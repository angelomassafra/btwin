"""
BTWIN - A toolkit for graph-based decision support system prototypes in building management

LLM MODULE
This module defines four things, in widening order of specificity:

- LLM, the connection to an OpenAI-compatible chat model (OpenRouter by default). It knows
  nothing about buildings, RDF or JSON-LD: any cycle can use it.
- CostMeter, which tallies the tokens and money a run spends.
- Tool, the individual steps a pipeline is built from - one model call, or one deterministic
  helper - each doing its one thing and returning. The prompts live here too.
- Cycle, one method per complete pipeline, chaining those steps. A cycle owns the control
  flow and nothing else.

Tools reuse the deterministic library rather than reimplementing it: RDF and SPARQL from
graph.py, Schema, Serialization and SpatialElement for the BTwin vocabulary and notation.

© Angelo Massafra, 2026
"""

# Dependencies
import base64
import copy
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

# BTWIN modules
from .document import Document
from .graph import RDF, SPARQL
from .property_set import Property, PropertySet
from .schema import Schema
from .serialization import Serialization
from .spatial_element import SpatialElement

# Type-only: langchain is an optional dependency, so these must never be imported at runtime
if TYPE_CHECKING:
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import Runnable
    from langchain_openai import ChatOpenAI

# --- Provider defaults ----------------------------------------------------------------
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Cheap and good enough to write SPARQL against a schema it is handed. Cheaper tiers exist
# (deepseek/deepseek-v4-flash, qwen/qwen3.7-flash); IDs churn, see openrouter.ai/models.
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
# OpenRouter attributes usage to these; they are optional but show up in the dashboard
APP_URL = "https://github.com/AngeloMassafra/btwin"
APP_TITLE = "btwin"


def _StripFences(text: str) -> str:
    """Remove ``` fences and a leading language tag that models like to add."""
    cleaned = text.strip()
    if "```" in cleaned:
        blocks = cleaned.split("```")
        if len(blocks) >= 2:
            cleaned = blocks[1]
    cleaned = cleaned.strip()
    if cleaned.lower().startswith("sparql"):
        cleaned = cleaned[len("sparql"):]
    return cleaned.strip()


def _SafeUID(text: str, fallback: str = "document") -> str:
    """
    Turn a file name into something usable as an '@id'.

    An '@id' becomes a relative IRI when the graph is serialised, and a space in it makes
    rdflib refuse to write Turtle at all - 'A3 PLN_244316736_1.pdf' is exactly that case. Only
    the characters an IRI path segment accepts unescaped survive.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._~-]+", "-", str(text)).strip("-.")
    return cleaned or fallback


def _ExtractJSON(text: str) -> str:
    """
    Pull a JSON document out of a reply.

    Fences and a stray sentence before or after the object are the two things models add, so
    the outermost '{' ... '}' is what actually matters. No braces at all means the model
    answered in prose: returning "" lets the caller say so plainly instead of reporting it as
    malformed JSON.
    """
    cleaned = text.strip()
    if "```" in cleaned:
        blocks = cleaned.split("```")
        if len(blocks) >= 2:
            cleaned = blocks[1]
    cleaned = cleaned.strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[len("json"):]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return cleaned[start:end + 1] if 0 <= start < end else ""


# Functions
class CostMeter():
    """
    Token and dollar tally for one run.

    OpenRouter reports the real charge for every call in usage.cost, which beats multiplying
    a price table: it already accounts for the provider it actually routed to, cached prompt
    tokens, and any discount. The table is only a fallback for calls that report no cost,
    such as BYOK keys.

    Unlike the rest of BTWIN this is a stateful object rather than a namespace of static
    methods, because a cost accumulates across calls and has to be carried between them.
    """

    def __init__(self, baseURL: str = OPENROUTER_BASE_URL, model: str = DEFAULT_MODEL):
        """
        Args:
            baseURL: Base URL used to fetch the price list when a call reports no cost.
            model: Model name assumed when a response does not name one.
        """
        self.baseURL = baseURL
        self.model = model
        self.calls: List[Dict[str, Any]] = []
        self._prices: Optional[Dict[str, Tuple[float, float]]] = None

    def Price(self, model: str) -> Tuple[float, float]:
        """
        Per-token prompt and completion price, read from the provider's model list once.

        Args:
            model: The model identifier to price.

        Returns:
            tuple[float, float]: (prompt price per token, completion price per token).
                (0.0, 0.0) when the list is unavailable or the model is not in it.
        """
        if self._prices is None:
            self._prices = {}
            try:
                import json as jsonlib
                import urllib.request
                with urllib.request.urlopen(f"{self.baseURL.rstrip('/')}/models", timeout=30) as response:
                    for entry in jsonlib.loads(response.read().decode("utf-8")).get("data", []):
                        pricing = entry.get("pricing") or {}
                        self._prices[entry.get("id", "")] = (
                            float(pricing.get("prompt") or 0.0),
                            float(pricing.get("completion") or 0.0),
                        )
            except Exception:
                pass   # no price list: the call is still counted, just without a cost
        return self._prices.get(model, (0.0, 0.0))

    def Record(self, agent: str, message: "AIMessage") -> Dict[str, Any]:
        """
        Log one completion's tokens and cost.

        Args:
            agent: Label for the step that made the call, e.g. 'agent 3 write'.
            message: The AIMessage returned by the model.

        Returns:
            dict: {'agent', 'model', 'promptTokens', 'completionTokens', 'cost', 'estimated'}.
                'estimated' is True when the cost came from the price table rather than
                from the provider.
        """
        metadata = getattr(message, "response_metadata", None) or {}
        usage = metadata.get("token_usage") or {}
        model = metadata.get("model_name") or self.model
        promptTokens = int(usage.get("prompt_tokens") or 0)
        completionTokens = int(usage.get("completion_tokens") or 0)

        cost, estimated = usage.get("cost"), False
        if cost is None:
            promptPrice, completionPrice = self.Price(model)
            cost = promptTokens * promptPrice + completionTokens * completionPrice
            estimated = True

        call = {
            "agent": agent,
            "model": model,
            "promptTokens": promptTokens,
            "completionTokens": completionTokens,
            "cost": float(cost),
            "estimated": estimated,
        }
        self.calls.append(call)
        return call

    def Total(self, start: int = 0) -> Dict[str, Any]:
        """
        Totals over the calls made from index `start` on, so one question can be subtotalled.

        Args:
            start: Index of the first call to include.

        Returns:
            dict: {'calls', 'promptTokens', 'completionTokens', 'cost', 'estimated'}.
        """
        window = self.calls[start:]
        return {
            "calls": len(window),
            "promptTokens": sum(c["promptTokens"] for c in window),
            "completionTokens": sum(c["completionTokens"] for c in window),
            "cost": sum(c["cost"] for c in window),
            "estimated": any(c["estimated"] for c in window),
        }

    @staticmethod
    def Format(amount: float) -> str:
        """A single call costs a few millionths of a dollar, so 2 decimals would read as $0.00."""
        return f"${amount:.6f}"

    @staticmethod
    def Describe(entry: Dict[str, Any]) -> str:
        """
        One-line token and cost summary for a single call or for a total.

        Args:
            entry: A dict from CostMeter.Record or CostMeter.Total.

        Returns:
            str: e.g. '1552+179 tokens, $0.000227'.
        """
        text = (f"{entry['promptTokens']}+{entry['completionTokens']} tokens, "
                f"{CostMeter.Format(entry['cost'])}")
        return text + " (estimated)" if entry.get("estimated") else text


class LLM():
    """
    The connection to a chat model. Nothing here knows what the model is being asked to do.
    """

    @staticmethod
    def Constructor(
        model: Optional[str] = None,
        apiKey: Optional[str] = None,
        *,
        baseURL: str = OPENROUTER_BASE_URL,
        temperature: float = 0.0,
        maxTokens: int = 2000,
        timeout: int = 120,
        maxRetries: int = 2,
        appURL: str = APP_URL,
        appTitle: str = APP_TITLE,
    ) -> "ChatOpenAI":
        """
        Build a chat model backed by an OpenAI-compatible endpoint, OpenRouter by default.

        OpenRouter speaks the OpenAI wire format, so ChatOpenAI drives it with nothing but a
        different base URL.

        Args:
            model: Model identifier. Defaults to $OPENROUTER_MODEL, else DEFAULT_MODEL.
            apiKey: API key. Defaults to $OPENROUTER_API_KEY.
            baseURL: Endpoint base URL.
            temperature: Sampling temperature. 0.0 so the same question gives the same answer.
            maxTokens: Upper bound on generated tokens per call. Raise it well above the
                default for a cycle that returns a whole document in one reply.
            timeout: Per-request timeout in seconds.
            maxRetries: Retries the client makes on transient failures.
            appURL: Sent as HTTP-Referer, used by OpenRouter for attribution.
            appTitle: Sent as X-Title, used by OpenRouter for attribution.

        Returns:
            ChatOpenAI: The configured chat model.

        Raises:
            ImportError: If `langchain-openai` is not installed.
            TypeError:   If argument types are invalid.
            ValueError:  If no API key is available.
        """
        try:
            from langchain_openai import ChatOpenAI
        except Exception as exc:
            raise ImportError(
                "langchain-openai is required. Install with `pip install btwin[llm]`."
            ) from exc

        if model is not None and not isinstance(model, str):
            raise TypeError("model must be a string if provided.")
        if apiKey is not None and not isinstance(apiKey, str):
            raise TypeError("apiKey must be a string if provided.")

        model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
        apiKey = (apiKey or os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if not apiKey:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        return ChatOpenAI(
            base_url=baseURL,
            api_key=apiKey,
            model=model,
            temperature=temperature,
            max_tokens=maxTokens,
            timeout=timeout,
            max_retries=maxRetries,
            default_headers={"HTTP-Referer": appURL, "X-Title": appTitle},
            # Makes OpenRouter return what the call actually cost, in usage.cost
            extra_body={"usage": {"include": True}},
        )

    @staticmethod
    def Chain(llm: "ChatOpenAI", systemPrompt: str) -> "Runnable":
        """
        Build a prompt | model chain. Agents differ only in their system prompt.

        Deliberately no StrOutputParser: it would hand back a bare string and throw away the
        usage and cost metadata riding on the message.

        Args:
            llm: A chat model from LLM.Constructor.
            systemPrompt: The system message. Braces in it are literal - see below.

        Returns:
            Runnable: The composed chain, taking {'input': str}.

        Raises:
            ImportError: If `langchain-core` is not installed.
            ValueError:  If inputs are missing.
        """
        try:
            from langchain_core.messages import SystemMessage
            from langchain_core.prompts import ChatPromptTemplate
        except Exception as exc:
            raise ImportError(
                "langchain-core is required. Install with `pip install btwin[llm]`."
            ) from exc

        if llm is None:
            raise ValueError("llm must be provided.")
        if not systemPrompt or not isinstance(systemPrompt, str):
            raise ValueError("systemPrompt must be a non-empty string.")

        # The system turn is a SystemMessage, not a ("system", text) pair: a pair is read as
        # an f-string template, so any prompt that shows the model a JSON shape would have to
        # double every brace, and forgetting to is a crash at call time rather than a typo.
        # Only the human turn stays a template, because {input} is the one field to fill.
        prompt = ChatPromptTemplate.from_messages([SystemMessage(content=systemPrompt),
                                                   ("human", "{input}")])
        return prompt | llm

    @staticmethod
    def Complete(
        llm: "ChatOpenAI",
        systemPrompt: str,
        prompt: str,
        meter: Optional[CostMeter] = None,
        agent: str = "",
        images: Optional[List[str]] = None,
    ) -> str:
        """
        Run one completion and return its text, tallying what it cost.

        Args:
            llm: A chat model from LLM.Constructor.
            systemPrompt: The system message defining the agent's job.
            prompt: The user message.
            meter: Optional CostMeter to record tokens and cost into.
            agent: Label recorded with the call, e.g. 'agent 3 write'.
            images: Optional data: URIs sent alongside the text, for a model that reads
                images. The model must accept image input; the OpenRouter default does.

        Returns:
            str: The model's reply, stripped.

        Raises:
            ImportError: If `langchain-core` is not installed.
            ValueError:  If inputs are missing.
            OSError:     If the provider could not be reached or returned an error. Every
                transport, auth and rate-limit failure is the same thing to the caller -
                the remote model did not answer.
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string.")

        try:
            if images:
                # A multimodal turn is built as messages rather than through a prompt
                # template: the template only carries a string, and its {} would have to be
                # escaped out of every document this ever reads.
                from langchain_core.messages import HumanMessage, SystemMessage
                content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
                content += [{"type": "image_url", "image_url": {"url": uri}} for uri in images]
                message = llm.invoke([SystemMessage(content=systemPrompt),
                                      HumanMessage(content=content)])
            else:
                message = LLM.Chain(llm, systemPrompt).invoke({"input": prompt})
        except ImportError:
            raise
        except Exception as exc:
            raise OSError(f"LLM request failed ({type(exc).__name__}): {exc}") from exc

        if meter is not None:
            meter.Record(agent, message)
        return str(message.content).strip()


class Tool():
    """
    The individual steps a cycle is built from: one model call, or one deterministic
    helper that prepares or checks what a model produced.

    Every method does one thing and returns. Nothing here loops, retries or decides what
    to run next - that is Cycle's job. The prompts live here too, beside the method that
    sends them.
    """

    # =================================================================================
    # Tools of cycle 1 - question about an RDF graph into SPARQL, and rows into an answer
    # =================================================================================

    RDF_WRITER_PROMPT = """You translate questions about a building knowledge graph into SPARQL 1.1.

Rules:
- Use ONLY the prefixes, classes and predicates listed in the GRAPH SCHEMA. Invent nothing.
- Always include the PREFIX lines for every prefix you use.
- Refer to individual entities by full IRI in angle brackets, e.g. <https://example.org/x>.
- Write a SELECT or an ASK query. Never INSERT, DELETE, DROP, LOAD or SERVICE.
- End a SELECT with LIMIT {limit} or less.
- Reply with the query and nothing else: no prose, no explanation, no markdown."""

    RDF_REPAIR_PROMPT = """You fix broken SPARQL 1.1 queries for a building knowledge graph.

You are given the schema, the query, and the exact reason it was rejected.
Return a corrected query using ONLY the vocabulary in the schema.
Reply with the query and nothing else: no prose, no explanation, no markdown."""

    RDF_ANSWER_PROMPT = """You answer questions about a building using ONLY the query results you are given.

- If the results are empty or do not cover the question, say so plainly.
- Never add a fact that is not in the results, and never guess a number.
- Be concise: two sentences at most."""

    # A query can use nothing but legal vocabulary, parse cleanly, and still match nothing,
    # because the model joined two classes that no predicate actually connects. That reads
    # exactly like an honest "no data" answer, so the empty result itself has to be the signal.
    RDF_EMPTY_RESULT_REASON = (
        "The query is valid but matched nothing in the graph. Every triple pattern must appear in "
        "the SHAPES list: check that each predicate really connects those two classes, and that you "
        "have not invented an extra hop between them. Rewrite it to follow the paths in the schema."
    )

    @staticmethod
    def RDFWriteSPARQL(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        meter: Optional[CostMeter] = None,
        rowLimit: int = 100,
    ) -> str:
        """
        Translate a natural-language question into a SPARQL query.

        The query is not checked here: SPARQL.Validate decides whether it is usable.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The graph schema as text, from RDF.SchemaSummary()['text'].
            question: The question in natural language.
            meter: Optional CostMeter to record tokens and cost into.
            rowLimit: The LIMIT the model is told not to exceed.

        Returns:
            str: The proposed SPARQL query, fences stripped.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not grounding or not isinstance(grounding, str):
            raise ValueError("grounding must be a non-empty string.")
        if not question or not isinstance(question, str):
            raise ValueError("question must be a non-empty string.")

        return _StripFences(LLM.Complete(
            llm,
            Tool.RDF_WRITER_PROMPT.format(limit=rowLimit),
            f"GRAPH SCHEMA\n{grounding}\n\nQUESTION\n{question.strip()}",
            meter,
            "agent 3 write",
        ))

    @staticmethod
    def RDFRepairSPARQL(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        sparql: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand a query back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The graph schema as text, from RDF.SchemaSummary()['text'].
            question: The original question in natural language.
            sparql: The query that was rejected.
            reason: Why it was rejected: a parse error, or RDF_EMPTY_RESULT_REASON.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The corrected SPARQL query, fences stripped.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not sparql or not isinstance(sparql, str):
            raise ValueError("sparql must be a non-empty string.")
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        return _StripFences(LLM.Complete(
            llm,
            Tool.RDF_REPAIR_PROMPT,
            f"GRAPH SCHEMA\n{grounding}\n\nQUESTION\n{question.strip()}\n\n"
            f"REJECTED QUERY\n{sparql}\n\nREASON\n{reason}",
            meter,
            "agent 4 repair",
        ))

    @staticmethod
    def RDFAnswer(
        llm: "ChatOpenAI",
        question: str,
        rows: List[Dict[str, Any]],
        meter: Optional[CostMeter] = None,
        rowLimit: int = 100,
    ) -> str:
        """
        Word an answer grounded in the retrieved rows and nothing else.

        Args:
            llm: A chat model from LLM.Constructor.
            question: The question in natural language.
            rows: The rows returned by RDF.Query. An empty list is a valid input and is
                reported to the model as such, so it says 'no results' instead of guessing.
            meter: Optional CostMeter to record tokens and cost into.
            rowLimit: How many rows to show the model.

        Returns:
            str: The natural-language answer.

        Raises:
            TypeError: If `rows` is not a list.
            OSError:   If the provider could not be reached.
        """
        if not isinstance(rows, list):
            raise TypeError("rows must be a list.")

        if rows:
            rendered = "\n".join(
                "; ".join(f"{k}={v}" for k, v in row.items() if v is not None)
                for row in rows[:rowLimit]
            )
        else:
            rendered = "(the query returned no rows)"

        return LLM.Complete(
            llm,
            Tool.RDF_ANSWER_PROMPT,
            f"QUESTION\n{question.strip()}\n\nQUERY RESULTS\n{rendered}",
            meter,
            "answer",
        )

    # =================================================================================
    # Tools of cycle 2 - a building description into JSON-LD, and the checks it must pass
    # =================================================================================

    JSONLD_WRITER_PROMPT = """You compile descriptions of buildings into BTwin JSON-LD.

Rules:
- Use ONLY the classes and relationships listed in the VOCABULARY. Invent nothing.
- Follow the NOTATION exactly: '@context' + '@graph', relationships nested under
  'relationships', every target repeating '@id' and '@type'.
- Emit EVERY node the description asks for. Do not abbreviate, do not summarise, do not
  write comments such as "... and so on": a partial graph is a wrong graph.
- '@id' must be unique and readable, derived from the hierarchy, e.g. BLDG-F2-S07-T1.
- Give every node a human-readable 'name'.
- Every relationship target must be the '@id' of a node that is also in '@graph'.
- Reply with the JSON document and nothing else: no prose, no explanation, no markdown."""

    JSONLD_REPAIR_PROMPT = """You fix BTwin JSON-LD documents.

You are given the vocabulary, the notation, the document and the exact reason it was rejected.
Return the corrected, COMPLETE document: every node must still be there.
Reply with the JSON document and nothing else: no prose, no explanation, no markdown."""

    @staticmethod
    def JSONLDVocabulary() -> Dict[str, Any]:
        """
        The vocabulary a generated graph is allowed to use.

        Serialization.IRIs() is the authority for classes and properties, because it is what
        Serialization.JSONLDByObjects enforces and what the graph is finally built from.
        Schema.RelationshipNames() adds which subject-object pairs each relationship permits.

        The two lists disagree - Schema.Types() knows 'ifc:Sensor' but not
        'brick:Temperature_Sensor', while the serializer knows the opposite - so the pair
        table is used only where it has something to say. See Tool.JSONLDLegalPair.

        Returns:
            dict: {'prefixes': dict, 'classes': set, 'properties': set, 'pairs': dict}.
        """
        iris = Serialization.IRIs()

        pairs: Dict[str, Set[Tuple[str, str]]] = {}
        for name, spec in Schema.RelationshipNames().items():
            pairs[name] = {
                (pair["subject"]["label"], pair["object"]["label"]) for pair in spec["pairs"]
            }

        return {
            "prefixes": iris["prefixes"],
            "classes": set(iris["classes"]),
            "properties": set(iris["properties"]),
            "pairs": pairs,
        }

    @staticmethod
    def JSONLDVocabularyBlock(vocabulary: Optional[Dict[str, Any]] = None) -> str:
        """
        Render the vocabulary as the text handed to the compiling agent.

        Args:
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.

        Returns:
            str: Prefixes, classes, relationships and legal pairs.
        """
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()

        lines = ["PREFIXES"]
        for prefix, iri in sorted(vocabulary["prefixes"].items()):
            lines.append(f"  {prefix}: {iri}")

        lines.append("\nCLASSES (allowed values of @type)")
        for name in sorted(vocabulary["classes"]):
            lines.append(f"  {name}")

        lines.append("\nRELATIONSHIPS (allowed keys inside 'relationships')")
        for name in sorted(vocabulary["properties"]):
            lines.append(f"  {name}")

        lines.append("\nLEGAL PAIRS (subject class -relationship-> allowed object classes)")
        for name in sorted(vocabulary["pairs"]):
            bySubject: Dict[str, List[str]] = {}
            for subject, obj in sorted(vocabulary["pairs"][name]):
                bySubject.setdefault(subject, []).append(obj)
            for subject, objects in bySubject.items():
                lines.append(f"  {subject} -{name}-> {' | '.join(objects)}")

        lines.append(
            "\nNOTES\n"
            "  Sensor classes such as brick:Temperature_Sensor are not in the pair table.\n"
            "  Attach them to the space they are in with brick:hasLocation."
        )
        return "\n".join(lines)

    @staticmethod
    def JSONLDNotationBlock() -> str:
        """
        A worked JSON-LD example, produced by the library rather than written out by hand.

        Generating it means the shape shown to the model cannot drift from the shape
        Serialization.JSONLDByObjects actually emits.

        Returns:
            str: The notation rules followed by a four-node example document.
        """
        building = SpatialElement.Constructor("BLDG", "bot:Building", "Building")
        storey = SpatialElement.Constructor("BLDG-F1", "bot:Storey", "Floor 1")
        space = SpatialElement.Constructor("BLDG-F1-S1", "bot:Space", "Space 1")
        SpatialElement.SetLocationRelationship(spatialElementObject=storey, linkedObject=building)
        SpatialElement.SetLocationRelationship(spatialElementObject=space, linkedObject=storey)

        example = Serialization.JSONLDByObjects(objects=[building, storey, space])
        # The constructors validate against Schema.Types(), which has no sensor classes, so
        # the sensor node is appended directly - the serializer accepts it, and it is the
        # case the model most needs to see.
        example["@graph"].append({
            "@id": "BLDG-F1-S1-T1",
            "@type": "brick:Temperature_Sensor",
            "relationships": {
                "brick:hasLocation": [{"@id": "BLDG-F1-S1", "@type": "bot:Space"}]
            },
            "name": "Temperature sensor 1",
        })

        return (
            "The document is a single JSON object with '@context' and '@graph'.\n"
            "Every node carries '@id', '@type', 'name' and a 'relationships' dict.\n"
            "Relationships are NOT top-level keys: they live inside 'relationships', and each\n"
            "target repeats the '@id' and the '@type' of the node it points at.\n\n"
            + json.dumps(example, indent=2)
        )

    @staticmethod
    def JSONLDLegalPair(vocabulary: Dict[str, Any], relationship: str,
                        subjectType: str, objectType: str) -> bool:
        """
        Whether a relationship may connect these two classes.

        Judged only when the pair table has an opinion about the subject class. A sensor class
        appears nowhere in it, so there is nothing to check and the pair is allowed; a
        bot:Space does appear, so pointing one straight at a bot:Site is caught.

        Args:
            vocabulary: The output of Tool.JSONLDVocabulary.
            relationship: The relationship name, e.g. 'brick:hasLocation'.
            subjectType: The class of the node carrying the relationship.
            objectType: The class of the node it points at.

        Returns:
            bool: True when the pair is allowed or cannot be judged.
        """
        pairs = vocabulary["pairs"].get(relationship)
        if not pairs:
            return True
        if subjectType not in {subject for subject, _ in pairs}:
            return True
        return (subjectType, objectType) in pairs

    @staticmethod
    def JSONLDValidate(
        document: Optional[str] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Check a compiled document before it is turned into a graph.

        The '@context' is not trusted but rebuilt from the prefixes actually used, which
        removes a whole class of failure the model would otherwise have to get right.

        Args:
            document: The model's reply, with or without fences and surrounding prose.
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.

        Returns:
            tuple: (the parsed document, "") when it holds, or (None, the reason) when not.
        """
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()

        text = _ExtractJSON(document or "")
        if not text:
            return None, "The reply contained no JSON document."

        try:
            jsonld = json.loads(text)
        except json.JSONDecodeError as exc:
            # Truncation lands here: the token ceiling was hit and the object never closed
            return None, f"The document is not valid JSON: {exc}"

        if not isinstance(jsonld, dict) or not isinstance(jsonld.get("@graph"), list):
            return None, "The document must be an object with a '@graph' list."
        nodes = jsonld["@graph"]
        if not nodes:
            return None, "'@graph' is empty."

        # --- nodes -------------------------------------------------------------------
        typeByID: Dict[str, str] = {}
        for position, node in enumerate(nodes):
            if not isinstance(node, dict):
                return None, f"Node {position} is not an object."
            nodeID, nodeType = node.get("@id"), node.get("@type")
            if not nodeID or not isinstance(nodeID, str):
                return None, f"Node {position} has no '@id'."
            if nodeID in typeByID:
                return None, f"'@id' {nodeID!r} is used by more than one node."
            if nodeType not in vocabulary["classes"]:
                return None, (f"Node {nodeID!r} has @type {nodeType!r}, which is not in the "
                              "vocabulary. Use only the listed classes.")
            typeByID[nodeID] = nodeType

        # --- relationships -----------------------------------------------------------
        for node in nodes:
            relationships = node.get("relationships", {})
            if not isinstance(relationships, dict):
                return None, f"Node {node['@id']!r} has a 'relationships' that is not an object."

            for name, targets in relationships.items():
                if name not in vocabulary["properties"]:
                    return None, (f"Node {node['@id']!r} uses relationship {name!r}, which is "
                                  "not in the vocabulary. Use only the listed relationships.")
                if not isinstance(targets, list):
                    return None, f"Relationship {name!r} on {node['@id']!r} must hold a list."

                for target in targets:
                    if not isinstance(target, dict) or not target.get("@id"):
                        return None, f"A target of {name!r} on {node['@id']!r} has no '@id'."
                    targetID = target["@id"]
                    if targetID not in typeByID:
                        return None, (f"Node {node['@id']!r} points at {targetID!r} through "
                                      f"{name!r}, but no node with that '@id' is in '@graph'.")
                    if target.get("@type") != typeByID[targetID]:
                        return None, (f"Target {targetID!r} of {name!r} on {node['@id']!r} is "
                                      f"declared as {target.get('@type')!r} but the node is "
                                      f"{typeByID[targetID]!r}.")
                    if not Tool.JSONLDLegalPair(vocabulary, name, node["@type"], typeByID[targetID]):
                        return None, (f"{node['@type']} -{name}-> {typeByID[targetID]} is not a "
                                      "legal pair. Check the LEGAL PAIRS list.")

        used = {name.split(":", 1)[0] for name in typeByID.values()}
        used |= {name.split(":", 1)[0] for node in nodes for name in node.get("relationships", {})}
        jsonld["@context"] = {
            prefix: iri for prefix, iri in vocabulary["prefixes"].items() if prefix in used
        }

        return jsonld, ""

    @staticmethod
    def JSONLDWrite(
        llm: "ChatOpenAI",
        vocabulary: str,
        notation: str,
        request: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Compile a description into a JSON-LD document.

        The document is not checked here: Tool.JSONLDValidate decides whether it is usable.

        Args:
            llm: A chat model from LLM.Constructor.
            vocabulary: The text from Tool.JSONLDVocabularyBlock.
            notation: The text from Tool.JSONLDNotationBlock.
            request: The building described in natural language.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The model's reply, to be handed to Tool.JSONLDValidate.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not request or not isinstance(request, str):
            raise ValueError("request must be a non-empty string.")

        return LLM.Complete(
            llm,
            Tool.JSONLD_WRITER_PROMPT,
            f"VOCABULARY\n{vocabulary}\n\nNOTATION\n{notation}\n\n"
            f"DESCRIPTION\n{request.strip()}",
            meter,
            "agent 1 compile",
        )

    @staticmethod
    def JSONLDRepair(
        llm: "ChatOpenAI",
        vocabulary: str,
        notation: str,
        request: str,
        document: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand a document back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            vocabulary: The text from Tool.JSONLDVocabularyBlock.
            notation: The text from Tool.JSONLDNotationBlock.
            request: The building described in natural language.
            document: The reply that was rejected.
            reason: Why it was rejected, from Tool.JSONLDValidate.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The corrected reply.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        return LLM.Complete(
            llm,
            Tool.JSONLD_REPAIR_PROMPT,
            f"VOCABULARY\n{vocabulary}\n\nNOTATION\n{notation}\n\n"
            f"DESCRIPTION\n{request.strip()}\n\n"
            f"REJECTED DOCUMENT\n{document}\n\nREASON\n{reason}",
            meter,
            "agent 2 repair",
        )


    # =================================================================================
    # Tools of cycle 3 - a PDF into a Document, a PropertySet and the node it belongs to
    # =================================================================================

    # What a property's value may be declared as. Kept short on purpose: a longer list only
    # gives the model more ways to be inconsistent, and these four cover a document's facts.
    DOCUMENT_QUANTITIES = ("IfcText", "IfcLabel", "IfcReal", "IfcInteger", "IfcBoolean")

    DOCUMENT_WRITER_PROMPT = """You read a building document and describe it as structured data.

Return ONE JSON object, and nothing else - no prose, no explanation, no markdown:

{
  "name": "a short human-readable name for the document",
  "linkTo": "the @id of the ONE node in CANDIDATES this document is about",
  "pset": {
    "name": "a short name for the set of properties",
    "properties": [
      {"name": "...", "value": ..., "quantity": "IfcText|IfcLabel|IfcReal|IfcInteger|IfcBoolean", "unit": "..."}
    ]
  }
}

Rules:
- 'name' must describe THE DOCUMENT YOU WERE GIVEN. The entries in CANDIDATES are other
  things already in the model: never copy a name from that list.
- 'linkTo' MUST be one of the @id values listed in CANDIDATES, copied exactly. Choose the
  most specific place the document is about - a Space, Storey, Zone, Building or Site -
  and prefer any of those over another Document or PropertySet.
- Every property value must come from the document. Never invent one, and never guess a
  number. Leave a property out rather than filling it with a placeholder.
- 'unit' is optional: give it only when the document states one.
- Use IfcReal or IfcInteger for numbers and write them as JSON numbers, not strings.
__MODE__"""

    DOCUMENT_AUTO_RULE = (
        "- Decide yourself which properties matter. Prefer the identifiers and quantities that\n"
        "  make the document findable later, and keep it to the ten most useful."
    )
    DOCUMENT_MANUAL_RULE = (
        "- The REQUEST names the property set and the properties to extract. Use exactly those\n"
        "  names, in that order, and add nothing else. If the document does not state one of\n"
        "  them, leave that property out rather than inventing a value."
    )

    DOCUMENT_REPAIR_PROMPT = """You fix a JSON description of a building document.

You are given the document, the candidate nodes, the JSON and the exact reason it was
rejected. Return the corrected JSON object and nothing else: no prose, no markdown."""

    @staticmethod
    def DocumentText(pdfPath) -> str:
        """
        The text layer of a PDF, page by page.

        Returns:
            str: The extracted text, empty when the PDF carries no text layer at all - which
                is what a scan looks like, and the signal to fall back to the page images.

        Raises:
            ImportError: If `pypdf` is not installed.
            OSError:     If the file is missing or cannot be read as a PDF.
        """
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise ImportError("pypdf is required. Install with `pip install btwin[pdf]`.") from exc

        path = Path(pdfPath)
        if not path.exists():
            raise OSError(f"PDF not found: {path}")
        try:
            reader = PdfReader(str(path))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception as exc:
            raise OSError(f"Could not read '{path}' as a PDF.") from exc

        return "\n\n".join(f"[page {i + 1}]\n{text}" for i, text in enumerate(pages) if text)

    @staticmethod
    def DocumentImages(pdfPath, maxPages: int = 4, dpi: int = 150) -> List[str]:
        """
        The pages of a PDF rendered to PNG data URIs, for a model that reads images.

        Args:
            pdfPath: The PDF to render.
            maxPages: How many pages to send. Every page costs tokens, and the facts worth
                extracting are almost always on the first ones.
            dpi: Rendering resolution. Below ~120 small print stops being legible.

        Returns:
            list[str]: One 'data:image/png;base64,...' URI per page.

        Raises:
            ImportError: If `pymupdf` is not installed.
            OSError:     If the file is missing or cannot be rendered.
        """
        try:
            import pymupdf
        except Exception:
            try:
                import fitz as pymupdf  # pymupdf < 1.24 installed itself as 'fitz'
            except Exception as exc:
                raise ImportError(
                    "pymupdf is required to read a PDF with no text layer. "
                    "Install with `pip install btwin[pdf]`."
                ) from exc

        path = Path(pdfPath)
        if not path.exists():
            raise OSError(f"PDF not found: {path}")
        if maxPages < 1:
            raise ValueError("maxPages must be at least 1.")

        images: List[str] = []
        try:
            document = pymupdf.open(str(path))
            for page in list(document)[:maxPages]:
                pixmap = page.get_pixmap(dpi=dpi)
                encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
                images.append(f"data:image/png;base64,{encoded}")
            document.close()
        except Exception as exc:
            raise OSError(f"Could not render '{path}'.") from exc

        return images

    @staticmethod
    def DocumentCandidates(objects: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, Dict[str, Any]]:
        """
        The nodes a document may be linked to, as text for the model and as a lookup.

        Args:
            objects: BTwin objects, the same list handed to Serialization.JSONLDByObjects.

        Returns:
            tuple: (the CANDIDATES block, {@id: object}).

        Raises:
            ValueError: If no usable object was supplied.
        """
        lookup: Dict[str, Any] = {}
        lines: List[str] = []
        for entry in objects or []:
            if not isinstance(entry, dict):
                continue
            uid = entry.get("@id")
            if not uid or uid in lookup:
                continue
            lookup[str(uid)] = entry
            name = entry.get("name")
            lines.append(f"  {uid}  |  {entry.get('@type', '?')}" + (f"  |  {name}" if name else ""))

        if not lookup:
            raise ValueError("objects must contain at least one BTwin object with an '@id'.")
        return "\n".join(lines), lookup

    @staticmethod
    def DocumentInfer(
        llm: "ChatOpenAI",
        content: str,
        candidates: str,
        request: str = "",
        mode: str = "auto",
        meter: Optional[CostMeter] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        """
        Ask the model to describe a document as name, property set and owning node.

        Args:
            llm: A chat model from LLM.Constructor.
            content: The document's text. Pass the pages as `images` instead when it is a scan.
            candidates: The block from Tool.DocumentCandidates.
            request: What the caller asked for. In 'manual' mode this names the property set
                and the properties to extract.
            mode: 'auto' lets the model choose the properties; 'manual' binds it to `request`.
            meter: Optional CostMeter to record tokens and cost into.
            images: Page images, used when the PDF has no text layer.

        Returns:
            str: The model's reply, to be handed to Tool.DocumentValidate.

        Raises:
            ValueError: If inputs are missing or `mode` is unknown.
            OSError:    If the provider could not be reached.
        """
        if mode not in ("auto", "manual"):
            raise ValueError("mode must be 'auto' or 'manual'.")
        if not candidates or not isinstance(candidates, str):
            raise ValueError("candidates must be a non-empty string.")
        if not (content or "").strip() and not images:
            raise ValueError("either content or images must be provided.")
        if mode == "manual" and not (request or "").strip():
            raise ValueError("manual mode needs a request naming the property set and properties.")

        rule = Tool.DOCUMENT_MANUAL_RULE if mode == "manual" else Tool.DOCUMENT_AUTO_RULE
        body = f"CANDIDATES\n{candidates}\n\nREQUEST\n{(request or '(none)').strip()}\n\n"
        body += "DOCUMENT\n(the pages are attached as images)" if images else f"DOCUMENT\n{content}"

        return LLM.Complete(
            llm,
            Tool.DOCUMENT_WRITER_PROMPT.replace("__MODE__", rule),
            body,
            meter,
            "agent 1 infer",
            images,
        )

    @staticmethod
    def DocumentValidate(
        reply: Optional[str] = None,
        candidates: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Check what the model returned before any of it becomes a BTwin object.

        Two passes earn their keep. `linkTo`: a plausible but invented '@id' would attach the
        document to a node that does not exist, and nothing downstream would notice. And the
        name: a model handed a list of existing nodes will sometimes name the document after
        one of them instead of after what it just read, which is silently wrong.

        Args:
            reply: The model's reply, with or without fences and surrounding prose.
            candidates: The {'@id': object} lookup from Tool.DocumentCandidates.

        Returns:
            tuple: (the parsed description, "") when it holds, or (None, the reason) when not.
        """
        candidates = candidates or {}
        text = _ExtractJSON(reply or "")
        if not text:
            return None, "The reply contained no JSON object."
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, f"The reply is not valid JSON: {exc}"
        if not isinstance(data, dict):
            return None, "The reply must be a single JSON object."

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            return None, "'name' must be a non-empty string."
        taken = {str(entry.get("name") or "").strip().lower()
                 for entry in candidates.values()} - {""}
        if name.strip().lower() in taken:
            return None, (f"'name' is {name!r}, which is the name of an existing node in "
                          "CANDIDATES. Name the document you were given, not another object.")

        linkTo = data.get("linkTo")
        if not isinstance(linkTo, str) or not linkTo.strip():
            return None, "'linkTo' must be the @id of one of the CANDIDATES."
        if candidates and linkTo not in candidates:
            return None, (f"'linkTo' is {linkTo!r}, which is not one of the CANDIDATES. "
                          "Copy one of the listed @id values exactly.")

        pset = data.get("pset")
        if not isinstance(pset, dict):
            return None, "'pset' must be an object with 'name' and 'properties'."
        if not isinstance(pset.get("name"), str) or not pset["name"].strip():
            return None, "'pset.name' must be a non-empty string."
        properties = pset.get("properties")
        if not isinstance(properties, list) or not properties:
            return None, "'pset.properties' must be a non-empty list."

        seen = set()
        for position, entry in enumerate(properties):
            if not isinstance(entry, dict):
                return None, f"Property {position} is not an object."
            propertyName = entry.get("name")
            if not isinstance(propertyName, str) or not propertyName.strip():
                return None, f"Property {position} has no 'name'."
            if propertyName in seen:
                return None, f"Property {propertyName!r} appears more than once."
            seen.add(propertyName)
            if "value" not in entry or entry["value"] is None or entry["value"] == "":
                return None, (f"Property {propertyName!r} has no value. Leave a property out "
                              "rather than sending an empty one.")
            quantity = entry.get("quantity")
            if quantity is not None and quantity not in Tool.DOCUMENT_QUANTITIES:
                return None, (f"Property {propertyName!r} declares quantity {quantity!r}. "
                              f"Use one of: {', '.join(Tool.DOCUMENT_QUANTITIES)}.")

        return data, ""

    @staticmethod
    def DocumentRepair(
        llm: "ChatOpenAI",
        content: str,
        candidates: str,
        reply: str,
        reason: str,
        request: str = "",
        meter: Optional[CostMeter] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        """
        Hand the description back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            content: The document's text, or '' when the pages travel as images.
            candidates: The block from Tool.DocumentCandidates.
            reply: The reply that was rejected.
            reason: Why it was rejected, from Tool.DocumentValidate.
            request: What the caller asked for.
            meter: Optional CostMeter to record tokens and cost into.
            images: Page images, when the PDF has no text layer.

        Returns:
            str: The corrected reply.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        body = f"CANDIDATES\n{candidates}\n\nREQUEST\n{(request or '(none)').strip()}\n\n"
        body += "DOCUMENT\n(the pages are attached as images)" if images else f"DOCUMENT\n{content}"
        body += f"\n\nREJECTED JSON\n{reply}\n\nREASON\n{reason}"

        return LLM.Complete(llm, Tool.DOCUMENT_REPAIR_PROMPT, body, meter, "agent 2 repair", images)

    # =================================================================================
    # Tools of cycle 4 - an editing instruction into a JSON-LD patch, and its application
    # =================================================================================

    # The operations a patch may carry. Nothing else is applied, so a key the model invents
    # is a rejection rather than a silently ignored instruction.
    JSONLD_EDIT_OPERATIONS = ("addNodes", "removeNodes", "addRelationships",
                              "removeRelationships", "renameNodes")

    JSONLD_EDITOR_PROMPT = """You edit BTwin JSON-LD documents by writing a patch.

You are given the vocabulary, the document as it stands, and what the user wants changed.
Return ONE JSON object holding ONLY the changes, and nothing else:

{
  "addNodes": [
    {"@id": "...", "@type": "...", "name": "...",
     "relationships": {"a relationship": [{"@id": "...", "@type": "..."}]}}
  ],
  "removeNodes": ["an @id"],
  "addRelationships": [{"subject": "an @id", "relationship": "...", "object": "an @id"}],
  "removeRelationships": [{"subject": "an @id", "relationship": "...", "object": "an @id"}],
  "renameNodes": [{"@id": "...", "name": "the new name"}]
}

Rules:
- Every key is optional: keep only the operations the request actually asks for.
- The patch is the CHANGE, not the result. Never restate a node the request leaves alone.
- Use ONLY the classes and relationships listed in the VOCABULARY. Invent nothing.
- Every '@id' you mention must already be in the DOCUMENT, or be added by this same patch,
  copied exactly as it is written there.
- A new '@id' must be unique and readable, derived from the hierarchy, e.g. BLDG-F2-S07-T1.
- Give every new node a human-readable 'name'.
- Removing a node also removes every relationship that points at it. Do not list those.
- Emit EVERY change the request asks for. Do not abbreviate and do not summarise: a partial
  patch is a wrong patch.
- Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    JSONLD_EDIT_REPAIR_PROMPT = """You fix patches for BTwin JSON-LD documents.

You are given the vocabulary, the document, the request, the patch and the exact reason it
was rejected. Return the corrected, COMPLETE patch: every change asked for must still be in it.
Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    @staticmethod
    def JSONLDDocumentBlock(jsonld: Optional[Dict[str, Any]] = None) -> str:
        """
        Render a document as the text handed to the editing agent.

        The nodes and the edges between them, not the JSON itself: an editor needs to know
        what is there and what it is called, and a patch costs the same to write either way.
        A large graph sent verbatim would spend most of the context on punctuation.

        Args:
            jsonld: The document to describe, as returned by Cycle.JSONLDCreateByPrompt.

        Returns:
            str: The node list followed by the relationship list.

        Raises:
            ValueError: If the document has no '@graph' list.
        """
        if not isinstance(jsonld, dict) or not isinstance(jsonld.get("@graph"), list):
            raise ValueError("jsonld must be an object with a '@graph' list.")

        nodes = [node for node in jsonld["@graph"] if isinstance(node, dict)]

        lines = [f"NODES ({len(nodes)}) - @id  a @type  'name'"]
        for node in nodes:
            name = node.get("name")
            lines.append(f"  {node.get('@id')}  a {node.get('@type')}"
                         + (f"  {name!r}" if name else ""))

        edges: List[str] = []
        for node in nodes:
            relationships = node.get("relationships")
            if not isinstance(relationships, dict):
                continue
            for name, targets in relationships.items():
                for target in targets if isinstance(targets, list) else []:
                    if isinstance(target, dict) and target.get("@id"):
                        edges.append(f"  {node.get('@id')} -{name}-> {target['@id']}")

        lines.append(f"\nRELATIONSHIPS ({len(edges)}) - subject -relationship-> object")
        lines.extend(edges)
        return "\n".join(lines)

    @staticmethod
    def JSONLDEditPatch(reply: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Read the patch out of the model's reply and check its shape.

        Shape only: whether the operations can be carried out against a particular document
        is Tool.JSONLDApplyEdit's question.

        Args:
            reply: The model's reply, with or without fences and surrounding prose.

        Returns:
            tuple: (the patch, "") when it holds, or (None, the reason) when it does not.
        """
        text = _ExtractJSON(reply or "")
        if not text:
            return None, "The reply contained no JSON patch."

        try:
            patch = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, f"The patch is not valid JSON: {exc}"

        if not isinstance(patch, dict):
            return None, "The patch must be a JSON object."

        unknown = sorted(set(patch) - set(Tool.JSONLD_EDIT_OPERATIONS))
        if unknown:
            return None, (f"The patch uses operation(s) {', '.join(unknown)}, which do not "
                          f"exist. Use only: {', '.join(Tool.JSONLD_EDIT_OPERATIONS)}.")

        for operation in Tool.JSONLD_EDIT_OPERATIONS:
            if operation in patch and not isinstance(patch[operation], list):
                return None, f"{operation!r} must hold a list."

        if not any(patch.get(operation) for operation in Tool.JSONLD_EDIT_OPERATIONS):
            return None, ("The patch is empty. Write the operations the request asks for, "
                          "using the '@id' values from the DOCUMENT.")

        return patch, ""

    @staticmethod
    def JSONLDApplyEdit(
        jsonld: Optional[Dict[str, Any]] = None,
        patch: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Apply a patch to a document, deterministically.

        The model decides what changes; this decides what the document then is. Nothing is
        applied unless every operation in the patch can be: a patch that names an '@id' the
        document does not carry is rejected whole, so a half-applied edit never reaches
        the caller.

        The order is fixed - nodes in, renames, relationships in, relationships out, nodes
        out - so a patch that adds a node and points at it in the same breath works, and
        removing a node takes the relationships aimed at it with it.

        Args:
            jsonld: The document to edit. It is not modified: the result is a deep copy.
            patch: The patch from Tool.JSONLDEditPatch.

        Returns:
            tuple: (the edited document, "") when it holds, or (None, the reason) when not.
        """
        if not isinstance(jsonld, dict) or not isinstance(jsonld.get("@graph"), list):
            return None, "The document must be an object with a '@graph' list."
        if not isinstance(patch, dict):
            return None, "The patch must be a JSON object."

        document = copy.deepcopy(jsonld)
        nodes: List[Dict[str, Any]] = [n for n in document["@graph"] if isinstance(n, dict)]
        byID: Dict[str, Dict[str, Any]] = {n["@id"]: n for n in nodes if isinstance(n.get("@id"), str)}

        def relationshipsOf(node: Dict[str, Any]) -> Dict[str, Any]:
            """The node's relationships dict, created when the node carries none."""
            if not isinstance(node.get("relationships"), dict):
                node["relationships"] = {}
            return node["relationships"]

        # --- nodes in ------------------------------------------------------------------
        for node in patch.get("addNodes") or []:
            if not isinstance(node, dict):
                return None, "Every entry of 'addNodes' must be a node object."
            nodeID = node.get("@id")
            if not nodeID or not isinstance(nodeID, str):
                return None, "A node in 'addNodes' has no '@id'."
            if nodeID in byID:
                return None, (f"'addNodes' adds {nodeID!r}, but a node with that '@id' is "
                              "already in the document. Pick another '@id'.")
            added = copy.deepcopy(node)
            relationshipsOf(added)
            document["@graph"].append(added)
            byID[nodeID] = added

        # --- renames -------------------------------------------------------------------
        for entry in patch.get("renameNodes") or []:
            if not isinstance(entry, dict):
                return None, "Every entry of 'renameNodes' must be an object."
            nodeID, name = entry.get("@id"), entry.get("name")
            if nodeID not in byID:
                return None, f"'renameNodes' names {nodeID!r}, which is not in the document."
            if not name or not isinstance(name, str):
                return None, f"The new name for {nodeID!r} must be a non-empty string."
            byID[nodeID]["name"] = name

        # --- relationships in ----------------------------------------------------------
        for entry in patch.get("addRelationships") or []:
            triple, error = Tool.JSONLDEditTriple(entry, byID, "addRelationships")
            if triple is None:
                return None, error
            subjectID, name, objectID = triple

            targets = relationshipsOf(byID[subjectID]).setdefault(name, [])
            if not isinstance(targets, list):
                return None, f"Relationship {name!r} on {subjectID!r} does not hold a list."
            # Re-adding an existing relationship is the edit already being in place, not a
            # failure: the document the caller asked for is the document they get either way.
            if not any(isinstance(t, dict) and t.get("@id") == objectID for t in targets):
                targets.append({"@id": objectID, "@type": byID[objectID].get("@type")})

        # --- relationships out ---------------------------------------------------------
        for entry in patch.get("removeRelationships") or []:
            triple, error = Tool.JSONLDEditTriple(entry, byID, "removeRelationships")
            if triple is None:
                return None, error
            subjectID, name, objectID = triple

            targets = relationshipsOf(byID[subjectID]).get(name)
            kept = [t for t in targets or [] if not (isinstance(t, dict) and t.get("@id") == objectID)]
            if targets is None or len(kept) == len(targets):
                return None, (f"'removeRelationships' removes {subjectID} -{name}-> {objectID}, "
                              "which is not in the document. Check the RELATIONSHIPS list.")
            if kept:
                byID[subjectID]["relationships"][name] = kept
            else:
                del byID[subjectID]["relationships"][name]

        # --- nodes out -----------------------------------------------------------------
        removed = patch.get("removeNodes") or []
        for nodeID in removed:
            if not isinstance(nodeID, str) or nodeID not in byID:
                return None, f"'removeNodes' names {nodeID!r}, which is not in the document."

        if removed:
            gone = set(removed)
            document["@graph"] = [n for n in document["@graph"]
                                  if not (isinstance(n, dict) and n.get("@id") in gone)]
            # Every relationship aimed at a removed node goes with it, or the document would
            # be left pointing at nodes that are no longer in '@graph'
            for node in document["@graph"]:
                relationships = node.get("relationships")
                if not isinstance(relationships, dict):
                    continue
                for name in list(relationships):
                    targets = relationships[name]
                    kept = [t for t in targets if not (isinstance(t, dict) and t.get("@id") in gone)]
                    if kept:
                        relationships[name] = kept
                    else:
                        del relationships[name]

        if not document["@graph"]:
            return None, "The patch empties the document: '@graph' would have no nodes left."

        return document, ""

    @staticmethod
    def JSONLDEditTriple(
        entry: Any,
        byID: Dict[str, Dict[str, Any]],
        operation: str,
    ) -> Tuple[Optional[Tuple[str, str, str]], str]:
        """
        Read one relationship operation and check both of its ends exist.

        Args:
            entry: One item of 'addRelationships' or 'removeRelationships'.
            byID: The nodes of the document being edited, by '@id'.
            operation: The operation the entry came from, named in the rejection.

        Returns:
            tuple: ((subject, relationship, object), "") when it holds, or (None, the reason).
        """
        if not isinstance(entry, dict):
            return None, f"Every entry of {operation!r} must be an object."

        subjectID = entry.get("subject")
        name = entry.get("relationship")
        objectID = entry.get("object")

        if not name or not isinstance(name, str):
            return None, f"An entry of {operation!r} has no 'relationship'."
        for role, nodeID in (("subject", subjectID), ("object", objectID)):
            if not isinstance(nodeID, str) or nodeID not in byID:
                return None, (f"The {role} {nodeID!r} of {name!r} in {operation!r} is not in "
                              "the document. Use an '@id' from the NODES list.")

        return (subjectID, name, objectID), ""

    @staticmethod
    def JSONLDEdit(
        llm: "ChatOpenAI",
        vocabulary: str,
        document: str,
        request: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Turn an editing instruction into a patch for an existing document.

        The patch is not checked here: Tool.JSONLDEditPatch and Tool.JSONLDApplyEdit decide
        whether it is usable.

        Args:
            llm: A chat model from LLM.Constructor.
            vocabulary: The text from Tool.JSONLDVocabularyBlock.
            document: The text from Tool.JSONLDDocumentBlock.
            request: What to change, in natural language.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The model's reply, to be handed to Tool.JSONLDEditPatch.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not request or not isinstance(request, str):
            raise ValueError("request must be a non-empty string.")

        return LLM.Complete(
            llm,
            Tool.JSONLD_EDITOR_PROMPT,
            f"VOCABULARY\n{vocabulary}\n\nDOCUMENT\n{document}\n\n"
            f"REQUEST\n{request.strip()}",
            meter,
            "agent 1 edit",
        )

    @staticmethod
    def JSONLDEditRepair(
        llm: "ChatOpenAI",
        vocabulary: str,
        document: str,
        request: str,
        patch: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand a patch back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            vocabulary: The text from Tool.JSONLDVocabularyBlock.
            document: The text from Tool.JSONLDDocumentBlock.
            request: What to change, in natural language.
            patch: The reply that was rejected.
            reason: Why it was rejected, from Tool.JSONLDEditPatch, Tool.JSONLDApplyEdit
                or Tool.JSONLDValidate.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The corrected reply.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        return LLM.Complete(
            llm,
            Tool.JSONLD_EDIT_REPAIR_PROMPT,
            f"VOCABULARY\n{vocabulary}\n\nDOCUMENT\n{document}\n\n"
            f"REQUEST\n{request.strip()}\n\n"
            f"REJECTED PATCH\n{patch}\n\nREASON\n{reason}",
            meter,
            "agent 2 repair",
        )

    # =================================================================================
    # Tools of cycle 5 - an editing instruction into a SPARQL update, and what it may touch
    # =================================================================================

    RDF_EDITOR_PROMPT = """You translate editing instructions for a building knowledge graph into SPARQL 1.1 Update.

Rules:
- Write ONE update: INSERT DATA, DELETE DATA, DELETE WHERE, or DELETE ... INSERT ... WHERE.
- Never DROP, CLEAR, LOAD, CREATE, ADD, MOVE, COPY or SERVICE, and never name a GRAPH:
  the edit belongs in the default graph.
- Always include the PREFIX lines for every prefix you use.
- Refer to existing entities by the full IRI the GRAPH SCHEMA lists for them, in angle
  brackets. Copy it exactly: an IRI that is one character off deletes nothing and adds a
  node nobody asked for.
- A new entity needs a new IRI of your own, built in the same namespace and shape as the
  entities already there, plus an rdf:type and an rdfs:label.
- Types and predicates must come from the GRAPH SCHEMA or from the ADDITIONAL VOCABULARY.
  Invent nothing.
- Deleting an entity means deleting every triple it is the subject of AND every triple that
  points at it. A DELETE WHERE with both patterns is the way to do it.
- Reply with the update and nothing else: no prose, no explanation, no markdown."""

    RDF_EDIT_REPAIR_PROMPT = """You fix SPARQL 1.1 Update statements for a building knowledge graph.

You are given the schema, the request, the update, and the exact reason it was rejected.
Return a corrected update using ONLY the vocabulary you were given.
Reply with the update and nothing else: no prose, no explanation, no markdown."""

    # An update can be legal, parse cleanly, run without complaint and change nothing at all,
    # because the model matched a pattern the graph does not hold. The caller sees a graph
    # that is simply unchanged, so the absence of a change has to be the signal.
    RDF_NO_CHANGE_REASON = (
        "The update is valid but changed nothing: no triple was added or removed. Check that "
        "every IRI is copied exactly from the ENTITIES list, and that each pattern in the WHERE "
        "clause really appears in the SHAPES list. Rewrite it against the paths in the schema."
    )

    @staticmethod
    def RDFEditVocabularyBlock(vocabulary: Optional[Dict[str, Any]] = None) -> str:
        """
        The classes and relationships an edit may introduce on top of the graph's own.

        An edit is the one operation that legitimately needs vocabulary the graph does not
        carry yet: the first sensor added to a building of rooms is a class the schema summary
        has never seen. The BTwin vocabulary is the authority for what may be introduced.

        Args:
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.

        Returns:
            str: The classes and relationships block, appended to the graph schema.
        """
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()

        lines = ["ADDITIONAL VOCABULARY (may be introduced by this edit)", "  CLASSES"]
        lines += [f"    {name}" for name in sorted(vocabulary["classes"])]
        lines.append("  PREDICATES")
        lines += [f"    {name}" for name in sorted(vocabulary["properties"])]
        return "\n".join(lines)

    @staticmethod
    def RDFEditTerms(
        schema: Optional[Dict[str, Any]] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
    ) -> Set[str]:
        """
        The CURIEs SPARQL.ValidateUpdate accepts in an edit.

        Wider than a query's, by exactly the BTwin vocabulary: what a query may ask about is
        bounded by what the graph holds, while what an edit may add is bounded by what the
        library knows how to represent.

        Args:
            schema: The output of RDF.SchemaSummary, for the graph's own vocabulary.
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.

        Returns:
            set[str]: The terms an update may use.
        """
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()

        terms: Set[str] = set(vocabulary["classes"]) | set(vocabulary["properties"])
        if schema:
            terms |= set(schema.get("terms") or set())
        return terms

    @staticmethod
    def RDFWriteUpdate(
        llm: "ChatOpenAI",
        grounding: str,
        request: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Translate an editing instruction into a SPARQL update.

        The update is not checked here: SPARQL.ValidateUpdate decides whether it is usable.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The graph schema as text, from RDF.SchemaSummary()['text'], followed
                by Tool.RDFEditVocabularyBlock.
            request: What to change, in natural language.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The proposed SPARQL update, fences stripped.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not grounding or not isinstance(grounding, str):
            raise ValueError("grounding must be a non-empty string.")
        if not request or not isinstance(request, str):
            raise ValueError("request must be a non-empty string.")

        return _StripFences(LLM.Complete(
            llm,
            Tool.RDF_EDITOR_PROMPT,
            f"GRAPH SCHEMA\n{grounding}\n\nREQUEST\n{request.strip()}",
            meter,
            "agent 1 edit",
        ))

    @staticmethod
    def RDFRepairUpdate(
        llm: "ChatOpenAI",
        grounding: str,
        request: str,
        sparql: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand an update back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The graph schema as text, as given to Tool.RDFWriteUpdate.
            request: The original instruction in natural language.
            sparql: The update that was rejected.
            reason: Why it was rejected: a parse error, a term that is not in the vocabulary,
                a failure to run, or RDF_NO_CHANGE_REASON.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The corrected SPARQL update, fences stripped.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not sparql or not isinstance(sparql, str):
            raise ValueError("sparql must be a non-empty string.")
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        return _StripFences(LLM.Complete(
            llm,
            Tool.RDF_EDIT_REPAIR_PROMPT,
            f"GRAPH SCHEMA\n{grounding}\n\nREQUEST\n{request.strip()}\n\n"
            f"REJECTED UPDATE\n{sparql}\n\nREASON\n{reason}",
            meter,
            "agent 2 repair",
        ))

    @staticmethod
    def RDFApplyUpdate(rdfGraph=None, sparql: Optional[str] = None):
        """
        Run an update against a copy of the graph and report what it changed.

        The caller's graph is never the one edited. An update is applied to a copy, and the
        copy is compared with the original: an update that damages the graph can be seen
        before anything is committed, and one that changes nothing can be told apart from
        one that worked.

        Args:
            rdfGraph: The rdflib.Graph to edit a copy of.
            sparql: The update, already through SPARQL.ValidateUpdate.

        Returns:
            tuple: (the edited copy, added triples, removed triples, "") when it ran, or
                (None, [], [], the reason) when it did not.

        Raises:
            ImportError: If `rdflib` is not installed.
            ValueError:  If inputs are missing.
        """
        try:
            from rdflib import Graph as RDFGraph
        except Exception as exc:
            raise ImportError("rdflib is required. Install with `pip install rdflib`.") from exc

        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")
        if not sparql or not isinstance(sparql, str):
            raise ValueError("sparql must be a non-empty string.")

        edited = RDFGraph()
        for prefix, namespace in rdfGraph.namespaces():
            edited.bind(prefix, namespace)
        edited += rdfGraph

        try:
            edited.update(sparql)
        except Exception as exc:
            # Parsed but would not run: the same kind of failure as a syntax error, and the
            # copy is discarded, so the caller's graph never saw it
            return None, [], [], f"The update failed to run: {exc}"

        before, after = set(rdfGraph), set(edited)
        return edited, sorted(after - before), sorted(before - after), ""

class Cycle():
    """
    Complete agent pipelines, one method each, chaining the steps in Tool.

    A cycle owns the control flow and nothing else: which tool runs when, how often a
    rejected result may be sent back, and what the caller gets at the end.
    """

    @staticmethod
    def RDFQueryByPrompt(
        rdfGraph=None,
        prompt: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Answer a natural-language question about an RDF graph, through a hosted LLM.

        A Graph-RAG pipeline of five steps, only three of which call a model:
        1. RDF.Index and 2. RDF.SchemaSummary describe the graph (no model);
        3. Tool.RDFWriteSPARQL turns the question into a query;
        4. SPARQL.Validate checks it, Tool.RDFRepairSPARQL rewrites it when it fails;
        5. RDF.Query runs it (no model), then Tool.RDFAnswer words the result.

        The facts come from the data, not from the model: the answer is written only from
        the rows the query returned.

        Args:
            rdfGraph: An rdflib.Graph instance to answer from.
            prompt: The question in natural language.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary, reused across questions when supplied.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected query may be sent back to be fixed.
            emptyRetries: How many times a valid but empty SELECT is rewritten.
            rowLimit: Maximum rows a generated SELECT may return.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'answer': str,        # the natural-language answer
                'sparql': str,        # the query that produced the rows
                'rows': list[dict],   # the retrieved rows
                'source': list[str],  # graph nodes the answer is grounded in
                'attempts': int,      # validation passes needed
                'usage': dict,        # tokens and cost for this question
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If inputs are missing, or no runnable query could be obtained.
            OSError:     If the model provider could not be reached.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")

        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = RDF.SchemaSummary(rdfGraph)
        meter = meter if meter is not None else CostMeter()

        # Where this question's calls start, so its cost can be split out of the run total
        first = len(meter.calls)

        sparql = Tool.RDFWriteSPARQL(llm, schema["text"], prompt, meter, rowLimit)
        if verbose:
            print(f"\n[agent 3] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 3] proposed query:\n{sparql}")

        # Agent 4 rejects, the repair chain rewrites, until it holds or the budget runs out
        attempts = 0
        for attempts in range(1, maxRepairs + 2):
            checked, error = SPARQL.Validate(sparql, schema["terms"], rowLimit)
            if checked is not None:
                sparql = checked
                break
            if verbose:
                print(f"[agent 4] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(f"No runnable query after {attempts} attempt(s). Last error: {error}")
            sparql = Tool.RDFRepairSPARQL(llm, schema["text"], prompt, sparql, error, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 4] repaired query:\n{sparql}")

        if verbose:
            print("[agent 4] accepted")

        rows = RDF.Query(rdfGraph, sparql)
        if verbose:
            print(f"[agent 5] {len(rows)} row(s), no model call")

        # An empty SELECT is the one failure the validator cannot see: legal vocabulary,
        # clean parse, wrong path. Give it back to the repair chain, but keep the rewrite
        # only if it actually finds rows - otherwise the original query stands and the empty
        # answer is real. ASK is left alone: false is an answer, not a miss.
        for retry in range(emptyRetries):
            if rows or SPARQL.Form(sparql) != "SELECT":
                break
            if verbose:
                print(f"[agent 4] empty result, asking for a rewrite ({retry + 1}/{emptyRetries})")

            candidate = Tool.RDFRepairSPARQL(
                llm, schema["text"], prompt, sparql, Tool.RDF_EMPTY_RESULT_REASON, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")

            checked, error = SPARQL.Validate(candidate, schema["terms"], rowLimit)
            if checked is None:
                if verbose:
                    print(f"[agent 4] rewrite rejected: {error} - keeping the empty result")
                break

            try:
                candidateRows = RDF.Query(rdfGraph, checked)
            except ValueError as exc:
                # prepareQuery accepted it but execution did not: keep what we already have
                if verbose:
                    print(f"[agent 5] rewrite failed to run: {exc} - keeping the empty result")
                break

            if verbose:
                print(f"[agent 4] rewritten query:\n{checked}")
                print(f"[agent 5] {len(candidateRows)} row(s) after rewrite")
            if candidateRows:
                sparql, rows = checked, candidateRows

        answer = Tool.RDFAnswer(llm, prompt, rows, meter, rowLimit)
        if verbose:
            print(f"[answer]  {CostMeter.Describe(meter.calls[-1])}")

        return {
            "answer": answer,
            "sparql": sparql,
            "rows": rows,
            "source": RDF.SourceNodes(rdfGraph, rows),
            "attempts": attempts,
            "usage": meter.Total(first),
        }

    @staticmethod
    def JSONLDCreateByPrompt(
        prompt: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Compile a natural-language description of a building into BTwin JSON-LD.

        Two agents: Tool.JSONLDWrite compiles the document, Tool.JSONLDValidate checks it
        against the BTwin vocabulary and Tool.JSONLDRepair rewrites it when it does not hold.

        The whole graph arrives in one reply, so build the model with a maxTokens high enough
        to hold it: a truncated reply is unparseable rather than partial.

        Args:
            prompt: The building described in natural language.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected document may be sent back to be fixed.
            verbose: Print each agent's outcome and cost as it goes.

        Returns:
            dict: {
                'jsonld': dict,    # the validated document, ready for NetworkX.ByJSONLD
                'attempts': int,   # validation passes needed
                'usage': dict,     # tokens and cost for this compilation
            }

        Raises:
            ImportError: If `langchain-openai` is not installed.
            ValueError:  If inputs are missing, or no valid document could be obtained.
            OSError:     If the model provider could not be reached.
        """
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")

        llm = llm if llm is not None else LLM.Constructor()
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()
        meter = meter if meter is not None else CostMeter()

        first = len(meter.calls)
        vocabularyText = Tool.JSONLDVocabularyBlock(vocabulary)
        notationText = Tool.JSONLDNotationBlock()

        document = Tool.JSONLDWrite(llm, vocabularyText, notationText, prompt, meter)
        if verbose:
            print(f"[agent 1] {CostMeter.Describe(meter.calls[-1])}")

        for attempts in range(1, maxRepairs + 2):
            jsonld, error = Tool.JSONLDValidate(document, vocabulary)
            if jsonld is not None:
                if verbose:
                    print(f"[agent 2] accepted after {attempts} pass(es), "
                          f"{len(jsonld['@graph'])} nodes")
                return {"jsonld": jsonld, "attempts": attempts, "usage": meter.Total(first)}

            if verbose:
                print(f"[agent 2] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(
                    f"No valid document after {attempts} attempt(s). Last error: {error}")

            document = Tool.JSONLDRepair(
                llm, vocabularyText, notationText, prompt, document, error, meter)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")

        raise ValueError("Unreachable.")   # the loop above either returns or raises

    @staticmethod
    def DocumentCreateByPrompt(
        pdfPath=None,
        prompt: str = "",
        *,
        objects: Optional[List[Dict[str, Any]]] = None,
        documentUID: Optional[str] = None,
        mode: str = "auto",
        llm: Optional["ChatOpenAI"] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        maxPages: int = 4,
        dpi: int = 150,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Read a PDF and build the Document, the PropertySet and the link it implies.

        Two agents: Tool.DocumentInfer describes the document as JSON, Tool.DocumentValidate
        checks it and Tool.DocumentRepair rewrites it when it does not hold. The BTwin objects
        are then built deterministically by Document, PropertySet and Property.

        The PDF is read as text when it has a text layer, and as page images when it does not:
        a scan carries no text at all, which is exactly the case the fallback exists for.

        Nothing is wired into the graph. The result names the node the document belongs to and
        leaves `SpatialElement.SetRelationship` to the caller, so a wrong inference can be seen
        before it reaches the data.

        Args:
            pdfPath: The PDF to read.
            prompt: What the caller wants. In 'manual' mode it names the property set and the
                properties to extract; in 'auto' mode it is optional context.
            objects: The BTwin objects the document may be linked to.
            documentUID: '@id' for the Document. Defaults to the file name without its
                suffix, with anything an IRI cannot carry replaced by '-'. An explicit
                value is used as given.
            mode: 'auto' lets the model choose the properties, 'manual' binds it to `prompt`.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected description may be sent back to be fixed.
            maxPages: Pages sent when falling back to images.
            dpi: Resolution used to render those pages.
            verbose: Print each agent's outcome and cost as it goes.

        Returns:
            dict: {
                'document': dict,       # the BTwin Document object
                'pset': dict,           # the PropertySet, properties already attached
                'linkTo': str,          # '@id' of the node the document is about
                'linkToObject': dict,   # that object, taken from `objects`
                'inferred': dict,       # exactly what the model returned, after validation
                'source': str,          # 'text' or 'images'
                'attempts': int,        # validation passes needed
                'usage': dict,          # tokens and cost for this document
            }

        Raises:
            ImportError: If `pypdf` (or `pymupdf`, for a scan) is not installed.
            ValueError:  If inputs are missing, or no valid description could be obtained.
            OSError:     If the PDF cannot be read, or the provider could not be reached.
        """
        if pdfPath is None:
            raise ValueError("pdfPath must be provided.")
        if mode not in ("auto", "manual"):
            raise ValueError("mode must be 'auto' or 'manual'.")

        path = Path(pdfPath)
        candidates, lookup = Tool.DocumentCandidates(objects)

        # Text when there is text, pages when there is not. A scan yields '' here, and that
        # emptiness is the only reliable tell that OCR-free extraction has nothing to give.
        content = Tool.DocumentText(path)
        images = None
        source = "text"
        if not content.strip():
            images = Tool.DocumentImages(path, maxPages=maxPages, dpi=dpi)
            source = "images"
            if verbose:
                print(f"[read] no text layer, sending {len(images)} page image(s)")
        elif verbose:
            print(f"[read] {len(content)} characters of text")

        llm = llm if llm is not None else LLM.Constructor()
        meter = meter if meter is not None else CostMeter()
        first = len(meter.calls)

        reply = Tool.DocumentInfer(llm, content, candidates, prompt, mode, meter, images)
        if verbose:
            print(f"[agent 1] {CostMeter.Describe(meter.calls[-1])}")

        inferred = None
        attempts = 0
        for attempts in range(1, maxRepairs + 2):
            inferred, error = Tool.DocumentValidate(reply, lookup)
            if inferred is not None:
                if verbose:
                    print(f"[agent 2] accepted after {attempts} pass(es)")
                break
            if verbose:
                print(f"[agent 2] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(
                    f"No valid description after {attempts} attempt(s). Last error: {error}")
            reply = Tool.DocumentRepair(
                llm, content, candidates, reply, error, prompt, meter, images)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")

        # --- Deterministic construction ------------------------------------------------
        document = Document.Constructor(
            documentObjectUID=str(documentUID) if documentUID else _SafeUID(path.stem),
            name=inferred["name"],
        )
        pset = PropertySet.Constructor(
            psetUID=f"{document['@id']}-PSET",
            psetName=inferred["pset"]["name"],
        )
        PropertySet.SetProperties(
            pset=pset,
            properties=[
                Property.Constructor(
                    propertyName=entry["name"],
                    propertyValue=entry["value"],
                    propertyQuantity=entry.get("quantity") or "IfcText",
                    propertyUnit=entry.get("unit"),
                )
                for entry in inferred["pset"]["properties"]
            ],
        )

        if verbose:
            print(f"[built]   '{inferred['name']}' -> {inferred['linkTo']}, "
                  f"{len(inferred['pset']['properties'])} propert(ies)")

        return {
            "document": document,
            "pset": pset,
            "linkTo": inferred["linkTo"],
            "linkToObject": lookup[inferred["linkTo"]],
            "inferred": inferred,
            "source": source,
            "attempts": attempts,
            "usage": meter.Total(first),
        }

    @staticmethod
    def JSONLDEditByPrompt(
        jsonld: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Change an existing BTwin JSON-LD document by describing the change.

        Cycle.JSONLDCreateByPrompt without the blank page: the document already exists, and the
        prompt says what to do to it - "add two spaces on floor 2", "remove the sensors in S07",
        "link the zone to the storey".

        Two agents and one rule the create cycle does not need: the model writes a PATCH, never
        the document. Tool.JSONLDEdit proposes the changes, Tool.JSONLDApplyEdit carries them
        out on a deep copy, Tool.JSONLDValidate checks the result, and Tool.JSONLDEditRepair
        rewrites the patch when either says no. A node the request never mentions cannot be
        dropped, renamed or reworded on the way through, and the reply stays the size of the
        edit rather than the size of the graph.

        Args:
            jsonld: The document to edit, as returned by Cycle.JSONLDCreateByPrompt. It is
                not modified: the result is a new document.
            prompt: The change, in natural language.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected patch may be sent back to be fixed.
            verbose: Print each agent's outcome and cost as it goes.

        Returns:
            dict: {
                'jsonld': dict,    # the edited document, ready for NetworkX.ByJSONLD
                'patch': dict,     # the changes that were applied
                'changes': dict,   # how many of each operation the patch carried
                'attempts': int,   # validation passes needed
                'usage': dict,     # tokens and cost for this edit
            }

        Raises:
            ImportError: If `langchain-openai` is not installed.
            ValueError:  If inputs are missing, or no valid edit could be obtained.
            OSError:     If the model provider could not be reached.
        """
        if not isinstance(jsonld, dict) or not isinstance(jsonld.get("@graph"), list):
            raise ValueError("jsonld must be a document with a '@graph' list.")
        if not jsonld["@graph"]:
            raise ValueError("jsonld has no nodes to edit.")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")

        llm = llm if llm is not None else LLM.Constructor()
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()
        meter = meter if meter is not None else CostMeter()

        first = len(meter.calls)
        vocabularyText = Tool.JSONLDVocabularyBlock(vocabulary)
        documentText = Tool.JSONLDDocumentBlock(jsonld)

        reply = Tool.JSONLDEdit(llm, vocabularyText, documentText, prompt, meter)
        if verbose:
            print(f"[agent 1] {CostMeter.Describe(meter.calls[-1])}")

        for attempts in range(1, maxRepairs + 2):
            # Three checks, one rejection path: the patch parses, it applies, and what it
            # produced is still a document the library would accept
            patch, error = Tool.JSONLDEditPatch(reply)
            edited = None
            if patch is not None:
                edited, error = Tool.JSONLDApplyEdit(jsonld, patch)
            if edited is not None:
                checked, error = Tool.JSONLDValidate(json.dumps(edited), vocabulary)
                if checked is not None:
                    changes = {name: len(patch.get(name) or [])
                               for name in Tool.JSONLD_EDIT_OPERATIONS}
                    if verbose:
                        print(f"[agent 2] accepted after {attempts} pass(es), "
                              + ", ".join(f"{count} {name}" for name, count in changes.items()
                                          if count)
                              + f" -> {len(checked['@graph'])} nodes")
                    return {"jsonld": checked, "patch": patch, "changes": changes,
                            "attempts": attempts, "usage": meter.Total(first)}

            if verbose:
                print(f"[agent 2] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(f"No valid edit after {attempts} attempt(s). Last error: {error}")

            reply = Tool.JSONLDEditRepair(
                llm, vocabularyText, documentText, prompt, reply, error, meter)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")

        raise ValueError("Unreachable.")   # the loop above either returns or raises

    @staticmethod
    def RDFEditByPrompt(
        rdfGraph=None,
        prompt: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        inPlace: bool = False,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Change an existing RDF graph by describing the change.

        Cycle.JSONLDEditByPrompt's counterpart on the triple side, and Cycle.RDFQueryByPrompt
        with the safety catch turned the other way: there the model writes a SELECT and may not
        write, here it writes an update and nothing else.

        Two agents: Tool.RDFWriteUpdate turns the instruction into SPARQL 1.1 Update,
        SPARQL.ValidateUpdate checks it, and Tool.RDFRepairUpdate rewrites it when it fails.
        Tool.RDFApplyUpdate then runs it against a COPY, so the caller's graph is only touched
        once an update has run and its effect has been seen.

        Three things bound what the model may do: the update must open with INSERT or DELETE,
        it may not name a graph or reach the network, and every CURIE in it must be in the
        graph's schema or in the BTwin vocabulary. New IRIs are the one thing it invents, and
        they have to be: a node being added does not exist yet.

        Args:
            rdfGraph: An rdflib.Graph to edit.
            prompt: The change, in natural language.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary, recomputed here when not supplied. It
                describes the graph BEFORE the edit: pass a fresh one for the next edit.
            vocabulary: The output of Tool.JSONLDVocabulary. Built here when not supplied.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected update may be sent back to be fixed.
            emptyRetries: How many times an update that changes nothing is rewritten.
            inPlace: When True, the change is committed to `rdfGraph` as well, and that same
                instance is returned. When False (default), the caller's graph is left as it
                was and only the edited copy is returned.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'graph': Graph,      # the edited graph
                'sparql': str,       # the update that produced it
                'added': list,       # triples added, as (subject, predicate, object) strings
                'removed': list,     # triples removed, in the same form
                'attempts': int,     # validation passes needed
                'usage': dict,       # tokens and cost for this edit
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If inputs are missing, or no runnable update could be obtained.
            OSError:     If the model provider could not be reached.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")

        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = RDF.SchemaSummary(rdfGraph)
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()
        meter = meter if meter is not None else CostMeter()

        first = len(meter.calls)
        grounding = f"{schema['text']}\n\n{Tool.RDFEditVocabularyBlock(vocabulary)}"
        terms = Tool.RDFEditTerms(schema, vocabulary)

        def rendered(triples) -> List[Tuple[str, str, str]]:
            """Triples as they read in the schema: compact where a prefix allows it."""
            return [tuple(RDF.Compact(rdfGraph, term) for term in triple) for triple in triples]

        def run(sparql: str, attempt: int) -> Tuple[Optional[Any], List, List, str]:
            """Validate, then apply to a copy. One rejection reason whichever step said no."""
            checked, error = SPARQL.ValidateUpdate(sparql, terms)
            if checked is None:
                return None, [], [], error
            edited, added, removed, error = Tool.RDFApplyUpdate(rdfGraph, checked)
            if edited is None:
                return None, [], [], error
            if verbose:
                print(f"[agent 4] accepted (pass {attempt})")
                print(f"[apply]   +{len(added)} / -{len(removed)} triple(s)")
            return edited, added, removed, ""

        sparql = Tool.RDFWriteUpdate(llm, grounding, prompt, meter)
        if verbose:
            print(f"\n[agent 3] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 3] proposed update:\n{sparql}")

        # Agent 4 rejects, the repair chain rewrites, until it runs or the budget runs out
        edited, added, removed, attempts = None, [], [], 0
        for attempts in range(1, maxRepairs + 2):
            edited, added, removed, error = run(sparql, attempts)
            if edited is not None:
                break
            if verbose:
                print(f"[agent 4] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(f"No runnable update after {attempts} attempt(s). Last error: {error}")
            sparql = Tool.RDFRepairUpdate(llm, grounding, prompt, sparql, error, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 4] repaired update:\n{sparql}")

        # An update that changes nothing is this cycle's empty SELECT: legal vocabulary, clean
        # parse, a pattern the data does not hold. Keep a rewrite only when it actually moves
        # a triple - otherwise the original stands and the caller is told plainly that the
        # graph is unchanged.
        for retry in range(emptyRetries):
            if added or removed:
                break
            if verbose:
                print(f"[agent 4] nothing changed, asking for a rewrite ({retry + 1}/{emptyRetries})")

            candidate = Tool.RDFRepairUpdate(
                llm, grounding, prompt, sparql, Tool.RDF_NO_CHANGE_REASON, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")

            edit, candidateAdded, candidateRemoved, error = run(candidate, attempts)
            if edit is None:
                if verbose:
                    print(f"[agent 4] rewrite rejected: {error} - keeping the unchanged graph")
                break
            if candidateAdded or candidateRemoved:
                sparql, edited = candidate, edit
                added, removed = candidateAdded, candidateRemoved

        # Only now, with an update that ran and a change that can be shown, is the caller's
        # own graph allowed to move
        if inPlace and (added or removed):
            for triple in removed:
                rdfGraph.remove(triple)
            for triple in added:
                rdfGraph.add(triple)
            edited = rdfGraph

        return {
            "graph": edited,
            "sparql": sparql,
            "added": rendered(added),
            "removed": rendered(removed),
            "attempts": attempts,
            "usage": meter.Total(first),
        }

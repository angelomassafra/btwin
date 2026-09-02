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
graph.py, Observation and SQL from point.py, Schema, Serialization and SpatialElement for the
BTwin vocabulary and notation.

© Angelo Massafra, 2026
"""

# Dependencies
import base64
import copy
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple, Union

# BTWIN modules
from .document import Document
from .graph import RDF, SPARQL
from .kpi_set import KPI, KPISet
from .point import SQL, Observation
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


def _ReadLine(prompt: str = "") -> Optional[str]:
    """
    Read one line from the console, or None when Escape was pressed.

    input() cannot see Escape. It returns a line only once Enter has been pressed, and the key
    is not part of one, so noticing it means reading a character at a time - which msvcrt does
    on Windows. Anywhere else the plain call is exactly right: another platform has no msvcrt,
    and a stdin that is a pipe rather than a console has no keystrokes to read at all.

    Args:
        prompt: Written before reading, as input() would.

    Returns:
        str | None: The line without its newline, or None if Escape ended it. An empty string
            is a blank line, which is not the same thing.

    Raises:
        EOFError:          At end of input, including Ctrl-Z on Windows.
        KeyboardInterrupt: On Ctrl-C, which getwch() returns as a character instead of raising.
    """
    try:
        import msvcrt
    except ImportError:
        return input(prompt)
    if not sys.stdin.isatty():
        return input(prompt)

    print(prompt, end="", flush=True)
    typed: List[str] = []
    while True:
        char = msvcrt.getwch()
        if char == "\x1b":               # Escape
            print()
            return None
        if char in ("\r", "\n"):
            print()
            return "".join(typed)
        if char == "\x03":               # Ctrl-C: a character here, not an exception
            print()
            raise KeyboardInterrupt
        if char == "\x1a":               # Ctrl-Z, end of input on Windows
            print()
            raise EOFError
        if char in ("\x00", "\xe0"):     # an arrow or function key: two characters, both dropped
            msvcrt.getwch()
            continue
        if char == "\x08":               # Backspace: erase it on screen as well as in the line
            if typed:
                typed.pop()
                print("\b \b", end="", flush=True)
            continue
        typed.append(char)
        # getwch() does not echo, so what was typed has to be written out to be seen
        print(char, end="", flush=True)


def _MintIRI(baseIRI: Optional[str], identifier: str) -> str:
    """
    The absolute IRI an '@id' will become once serialized, by RDF.ByJSONLD's own rule.

    Needed before serialization, not after: a KPI has to be looked up in the graph to know
    whether recording it would overwrite one already there, and that lookup happens while the
    figures are still BTwin dictionaries. Getting the rule wrong here would mean checking for
    a node under a name the writer never uses, and reporting every overwrite as a new record.
    """
    if baseIRI and "://" not in identifier:
        separator = "" if baseIRI.endswith(("#", "/", ":")) else "#"
        return f"{baseIRI}{separator}{identifier}"
    return identifier


def _NoData(rows: List[Dict[str, Any]]) -> bool:
    """
    Whether a result carries no data, whatever its row count.

    'No rows' is not how SQL usually reports finding nothing. A bare aggregate over a WHERE
    clause that matched nothing comes back as ONE row of NULLs - `SELECT MAX(value) ... WHERE
    (no match)` is `[{'m': None}]`, not `[]` - so a cycle that tests `if rows` reads the most
    common miss there is as a successful answer, and hands the answering agent a None to
    describe. All-NULL is the honest test: a row of nothing but NULLs says the same thing an
    empty result does, and a real answer that consisted solely of NULLs would too.
    """
    return all(value is None for row in rows for value in row.values())


def _NoMatch(rows: List[Dict[str, Any]]) -> bool:
    """
    _NoData's counterpart for SPARQL, where a miss comes back as zero rather than NULL.

    SQL answers a bare aggregate over an unmatched WHERE with NULL; SPARQL answers it with a
    number. `SELECT (COUNT(?s) AS ?n) (SUM(?a) AS ?total)` over a pattern that joins to
    nothing is `[{'n': '0', 'total': '0'}]` - one row, both bound, and indistinguishable from
    a building that genuinely has no spaces. So an empty result is not the only shape a wrong
    path takes, and testing `if rows` reads the commonest one as an answer.

    A row of nothing but zeros, empties and NULLs is treated as a miss. It costs one rewrite
    in the rare case where zero was the truth, and the original query still stands when the
    rewrite finds nothing better.
    """
    if not rows:
        return True
    if len(rows) != 1:
        return False
    for value in rows[0].values():
        if value is None or value == "":
            continue
        try:
            if float(value) == 0.0:
                continue
        except (TypeError, ValueError):
            pass
        return False
    return True


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
        "The query is valid but matched nothing in the graph - and a COUNT of 0 or a SUM of 0 is "
        "that same miss, not an answer. Every triple pattern must appear in the SHAPES list AND run "
        "in the direction SHAPES gives it: a predicate that goes from Space to Storey does not also "
        "go from Storey to Space, and using it both ways in one query joins to nothing. Check that "
        "each predicate really connects those two classes, that none is reversed, and that you have "
        "not invented an extra hop between them. Rewrite it to follow the paths in the schema."
    )

    @staticmethod
    def RDFChainBlock(chains: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Render RDF.Chains as the grounding block that follows the schema.

        SHAPES gives the writer one hop at a time and leaves it to compose them. Composing is
        where the query goes wrong, in the two ways the note below names, so the paths are
        handed over already composed and with a worked example against them.

        Args:
            chains: The output of RDF.Chains.

        Returns:
            str: The block, or '' when there are no chains - a graph too shallow to have a
                two-hop path has nothing to add, and an empty heading would only invite the
                model to invent one.

        Raises:
            TypeError: If `chains` is not a list.
        """
        if chains is None:
            chains = []
        if not isinstance(chains, list):
            raise TypeError("chains must be a list.")
        if not chains:
            return ""

        lines = ["GRAPH CHAINS (multi-hop paths the data really walks, one example each)"]
        for chain in chains:
            lines.append(f"  {chain['template']}")
            lines.append(f"    e.g. {chain['example']}")
        lines.append(
            "  Read a chain left to right: the subject of each hop is on its left. Reversing a\n"
            "  hop, or joining two hops into a path that is not listed here, gives a query that\n"
            "  is still valid, still parses, and still matches nothing.\n"
            "  The examples name things by label, to be read - take IRIs from ENTITIES."
        )
        return "\n".join(lines)

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

    # =================================================================================
    # Tools of cycle 6 - a chat turn into an intent and a request that stands on its own
    # =================================================================================

    # What a turn may be routed to. 'talk' is the one that touches no graph: it covers
    # greetings and questions about the conversation itself, which would otherwise be
    # translated into SPARQL and answered, confidently, with an empty result.
    CHAT_INTENTS = ("question", "edit", "talk")

    CHAT_ROUTER_PROMPT = """You route the turns of a conversation about a building knowledge graph.

Read the conversation so far and the new message, then reply with ONE JSON object:
{"intent": "question" | "edit" | "talk", "request": "the message, rewritten to stand alone"}

Choose the intent:
- "question" - it asks for something the graph records: what, which, how many, where, list.
- "edit" - it asks to add, rename, change or remove something in the graph.
- "talk" - anything else: a greeting, thanks, or a question about the conversation itself
  ("what did I just ask?", "explain that query").

Write the request:
- Resolve every pronoun and every ellipsis against the conversation, so that someone who has
  not read it can still act on the request. After a question about the first floor, "and the
  second one?" becomes "Which sensors are on the second floor?".
- Change nothing else. Keep the user's wording, their level of detail and their language.
- For "talk", repeat the message unchanged.

Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    CHAT_TALK_PROMPT = """You are the assistant in a conversation about a building knowledge graph.

This turn asked nothing of the graph, so you have no data to answer from - only the conversation.

- Answer from the conversation alone. Never state a fact about the building that is not
  already in it.
- If answering would need something only the graph holds, say so and invite the user to ask it.
- Reply in the user's language. Three sentences at most."""

    # The same two jobs, worded for a table. Routing and small talk are the only steps that
    # need to know what the conversation is about, because they are the only ones that read
    # the user's words before anything has been retrieved.
    CHAT_TABLE_ROUTER_PROMPT = """You route the turns of a conversation about a table of building measurements.

The table holds one row per observation: which sensor made it, what it measured, in what
unit, the value, and when.

Read the conversation so far and the new message, then reply with ONE JSON object:
{"intent": "question" | "edit" | "talk", "request": "the message, rewritten to stand alone"}

Choose the intent:
- "question" - it asks for something the readings show: what, which, how much, how many,
  when, compare, list, is there a pattern.
- "edit" - it asks to correct a reading, delete one, or record a new one.
- "talk" - anything else: a greeting, thanks, or a question about the conversation itself
  ("what did I just ask?", "explain that query").

Write the request:
- Resolve every pronoun and every ellipsis against the conversation, so that someone who has
  not read it can still act on the request. After a question about January, "and February?"
  becomes "What was the electricity consumption in February?".
- Carry forward the sensor, the quantity and the period the conversation has settled on: a
  follow-up that drops them means the same ones, not all of them.
- Change nothing else. Keep the user's wording, their level of detail and their language.
- For "talk", repeat the message unchanged.

Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    CHAT_TABLE_TALK_PROMPT = """You are the assistant in a conversation about a table of building measurements.

This turn asked nothing of the table, so you have no data to answer from - only the conversation.

- Answer from the conversation alone. Never state a figure about the building that is not
  already in it.
- If answering would need a reading only the table holds, say so and invite the user to ask it.
- Reply in the user's language. Three sentences at most."""

    @staticmethod
    def ChatTranscript(
        history: Optional[List[Dict[str, Any]]] = None,
        maxTurns: int = 8,
        answerChars: int = 240,
    ) -> str:
        """
        Render past turns as the text block a chat agent is given to read. No model call.

        Only the last `maxTurns` survive, and each answer is cut to `answerChars`. A
        conversation otherwise grows without bound, and every turn would be billed the whole
        history back to the first one.

        The resolved request is shown next to the message it came from, so a chain of
        follow-ups resolves against what was understood rather than against the ellipsis:
        two turns after 'and the second one?', the router can still see 'the second floor'.

        Args:
            history: Turns as recorded by Cycle.RDFChatTurn, each a dict with 'message',
                'intent', 'request' and 'answer'.
            maxTurns: How many of the most recent turns to render. 0 or less renders all.
            answerChars: Where to cut a long answer.

        Returns:
            str: The transcript, or '(no conversation yet)' when there is none. Never empty:
                an empty section under a heading reads to a model like a missing one.

        Raises:
            TypeError: If `history` is not a list.
        """
        if history is None:
            history = []
        if not isinstance(history, list):
            raise TypeError("history must be a list.")

        recent = history[-maxTurns:] if maxTurns > 0 else history
        if not recent:
            return "(no conversation yet)"

        lines: List[str] = []
        for number, turn in enumerate(recent, start=len(history) - len(recent) + 1):
            message = str(turn.get("message") or "").strip()
            request = str(turn.get("request") or "").strip()
            intent = str(turn.get("intent") or "").strip()
            answer = " ".join(str(turn.get("answer") or "").split())
            if len(answer) > answerChars:
                answer = answer[:answerChars].rstrip() + "..."

            lines.append(f"[{number}] user: {message}")
            if request and request != message:
                lines.append(f"     understood as ({intent}): {request}")
            lines.append(f"     assistant: {answer or '(no answer)'}")
        return "\n".join(lines)

    @staticmethod
    def ChatRoute(
        llm: "ChatOpenAI",
        transcript: Optional[str] = None,
        message: Optional[str] = None,
        meter: Optional[CostMeter] = None,
        systemPrompt: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Decide what a chat turn is asking for, and restate it so it stands on its own.

        This is the only place a chat's memory is used. The cycles it feeds -
        Cycle.RDFQueryByPrompt and Cycle.RDFEditByPrompt, or their SQLite counterparts - each
        take one self-contained prompt and know nothing of any conversation, so resolving the
        ellipsis here leaves them exactly as they are, and keeps the transcript out of the
        window where an answer is written from retrieved rows.

        Args:
            llm: A chat model from LLM.Constructor.
            transcript: The conversation so far, from Tool.ChatTranscript.
            message: What the user just typed.
            meter: Optional CostMeter to record tokens and cost into.
            systemPrompt: Which router to use. Defaults to Tool.CHAT_ROUTER_PROMPT, for a
                graph; Cycle.SQLiteChatTurn passes Tool.CHAT_TABLE_ROUTER_PROMPT. The three
                intents and the reply format are the same either way, which is why the
                parsing below is shared: only the wording of what counts as a question or an
                edit changes with the subject.

        Returns:
            dict: {'intent': one of Tool.CHAT_INTENTS, 'request': the standalone request}

        Raises:
            ValueError: If `message` is missing.
            OSError:    If the provider could not be reached.
        """
        if not message or not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")
        transcript = (transcript or "").strip() or "(no conversation yet)"

        reply = LLM.Complete(
            llm,
            systemPrompt or Tool.CHAT_ROUTER_PROMPT,
            f"CONVERSATION SO FAR\n{transcript}\n\nNEW MESSAGE\n{message.strip()}",
            meter,
            "router",
        )

        # A router that answers in prose, or invents a fourth intent, must not end the
        # conversation: the message itself is always a usable request, and 'question' is the
        # intent that reads the graph without changing it.
        intent, request = "question", message.strip()
        try:
            parsed = json.loads(_ExtractJSON(reply))
        except (ValueError, TypeError):
            parsed = {}
        if isinstance(parsed, dict):
            candidate = str(parsed.get("intent") or "").strip().lower()
            if candidate in Tool.CHAT_INTENTS:
                intent = candidate
            restated = str(parsed.get("request") or "").strip()
            if restated:
                request = restated

        return {"intent": intent, "request": request}

    @staticmethod
    def ChatReply(
        llm: "ChatOpenAI",
        transcript: Optional[str] = None,
        message: Optional[str] = None,
        meter: Optional[CostMeter] = None,
        systemPrompt: Optional[str] = None,
    ) -> str:
        """
        Answer a turn that asks nothing of the graph, from the conversation alone.

        The counterpart of Tool.RDFAnswer for the 'talk' intent: there the grounding is the
        rows a query returned, here it is the transcript, and in neither case may the model
        add a fact of its own.

        Args:
            llm: A chat model from LLM.Constructor.
            transcript: The conversation so far, from Tool.ChatTranscript.
            message: What the user just typed.
            meter: Optional CostMeter to record tokens and cost into.
            systemPrompt: Defaults to Tool.CHAT_TALK_PROMPT, for a graph;
                Cycle.SQLiteChatTurn passes Tool.CHAT_TABLE_TALK_PROMPT.

        Returns:
            str: The reply.

        Raises:
            ValueError: If `message` is missing.
            OSError:    If the provider could not be reached.
        """
        if not message or not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")
        transcript = (transcript or "").strip() or "(no conversation yet)"

        return LLM.Complete(
            llm,
            systemPrompt or Tool.CHAT_TALK_PROMPT,
            f"CONVERSATION SO FAR\n{transcript}\n\nNEW MESSAGE\n{message.strip()}",
            meter,
            "talk",
        )

    # =================================================================================
    # Tools of cycle 7 - question about an observation table into SQL, and rows into an answer
    # =================================================================================

    SQLITE_WRITER_PROMPT = """You translate questions about building observation data into SQLite SQL.

Rules:
- Query ONLY the table named in the TABLE section, using ONLY the columns listed in COLUMNS.
  Invent no column, no table and no join.
- Filter string columns on the literals given in VALUES, spelled exactly as they appear there.
- Double-quote every column name that contains ':' or a space, e.g. "sosa:madeBySensor".
- This is SQLite: read time with strftime on the timestamp column. There is no EXTRACT,
  DATEPART, DATE_TRUNC or TO_CHAR.
- The table covers the fixed period COLUMNS gives for the timestamp, and today's date is not
  inside it. Read 'this week', 'last month' or 'recently' as a period within that range - the
  most recent one - never as something computed from the current date. Never write 'now',
  date('now') or CURRENT_TIMESTAMP: they filter the table down to nothing.
- Write ONE read-only SELECT (a WITH ... SELECT is fine). Never INSERT, UPDATE, DELETE,
  DROP, ALTER, CREATE, ATTACH or PRAGMA, and never two statements.
- Aggregate in SQL rather than returning raw rows to be added up: a question about a total,
  a ranking or a monthly profile is a SUM or an AVG with a GROUP BY.
- When you build a group key out of part of an identifier, check it against VALUES first:
  a substring that is not unique across those literals silently merges rows that belong to
  different things, and the total it reports will be wrong.
- Never write ORDER BY ... LIMIT 1 to find a highest or lowest. Return the whole ordered
  ranking and let the answer read the top row off it: one row on its own cannot be checked
  against anything, and it silently discards the rest of a question - 'show the monthly
  profile, and when did it peak' needs all twelve months, not the biggest one.
- LIMIT is a ceiling that stops a runaway query, not the size of the answer.
- When the question is about one particular sensor, building, campus or period, SELECT the
  column that identifies it alongside the aggregate - never the bare number on its own. A
  lone total carries no trace of what was filtered to produce it, so a WHERE clause that
  picked the wrong one is reported with exactly the confidence of the right one, and nothing
  downstream can tell.
- Give every computed column a readable alias, e.g. SUM(value) AS totalKWh.
- End with LIMIT {limit} or less.
- Reply with the query and nothing else: no prose, no explanation, no markdown."""

    SQLITE_REPAIR_PROMPT = """You fix broken SQLite queries over a building observation table.

You are given the table description, the query, and the exact reason it was rejected.
Return a corrected read-only SELECT using ONLY the columns and literal values in the
description. Reply with the query and nothing else: no prose, no explanation, no markdown."""

    SQLITE_ANSWER_PROMPT = """You answer questions about a building's measured data using ONLY the query results you are given.

- If the results are empty or do not cover the question, say so plainly.
- Never add a number that is not in the results, and never estimate one.
- Quote figures as they are given, with the unit the results carry.
- Be concise: three sentences at most, or a short list when the results are a ranking."""

    # A query can name only real columns, compile cleanly, and still match nothing, because
    # the model filtered on a literal that is not in the table - 'Electricity' where the data
    # says 'ElectricityConsumption', or a year outside the range the table covers. That reads
    # exactly like an honest "no data" answer, so the empty result itself has to be the signal.
    SQLITE_EMPTY_RESULT_REASON = (
        "The query is valid but matched no rows. That is almost always a WHERE clause: check "
        "every literal you filtered on against the VALUES section, spelled exactly, and check "
        "that the period you asked for is inside the range the timestamp column spans. Widen "
        "or correct the filter and try again."
    )

    @staticmethod
    def SQLiteWriteSQL(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        meter: Optional[CostMeter] = None,
        rowLimit: int = 100,
    ) -> str:
        """
        Translate a natural-language question into a SQLite query.

        The query is not checked here: SQL.Validate decides whether it is usable.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The table description, from Observation.SQLiteSchemaSummary()['text'].
            question: The question in natural language.
            meter: Optional CostMeter to record tokens and cost into.
            rowLimit: The LIMIT the model is told not to exceed.

        Returns:
            str: The proposed SQL query, fences stripped.

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
            Tool.SQLITE_WRITER_PROMPT.format(limit=rowLimit),
            f"TABLE DESCRIPTION\n{grounding}\n\nQUESTION\n{question.strip()}",
            meter,
            "agent 3 write",
        ))

    @staticmethod
    def SQLiteRepairSQL(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        sql: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand a query back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The table description, from Observation.SQLiteSchemaSummary()['text'].
            question: The original question in natural language.
            sql: The query that was rejected.
            reason: Why it was rejected: SQLite's own compilation error, a safety refusal,
                or SQLITE_EMPTY_RESULT_REASON.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The corrected SQL query, fences stripped.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not sql or not isinstance(sql, str):
            raise ValueError("sql must be a non-empty string.")
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        return _StripFences(LLM.Complete(
            llm,
            Tool.SQLITE_REPAIR_PROMPT,
            f"TABLE DESCRIPTION\n{grounding}\n\nQUESTION\n{question.strip()}\n\n"
            f"REJECTED QUERY\n{sql}\n\nREASON\n{reason}",
            meter,
            "agent 4 repair",
        ))

    @staticmethod
    def SQLiteAnswer(
        llm: "ChatOpenAI",
        question: str,
        rows: List[Dict[str, Any]],
        meter: Optional[CostMeter] = None,
        rowLimit: int = 100,
    ) -> str:
        """
        Word an answer grounded in the retrieved rows and nothing else.

        The counterpart of Tool.RDFAnswer for a table. It differs in one way that matters:
        SQLite hands back real floats, so a rendered row can carry a number with sixteen
        digits after the point. They are shown as they are - rounding here would put a figure
        in front of the model that is not the one in the database.

        Args:
            llm: A chat model from LLM.Constructor.
            question: The question in natural language.
            rows: The rows returned by Observation.SQLiteFetch. An empty list is a valid
                input and is reported to the model as such, so it says 'no results' instead
                of guessing.
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
            Tool.SQLITE_ANSWER_PROMPT,
            f"QUESTION\n{question.strip()}\n\nQUERY RESULTS\n{rendered}",
            meter,
            "answer",
        )

    # =================================================================================
    # Tools of cycle 8 - an editing instruction into a SQL update, and what it may touch
    # =================================================================================

    SQLITE_EDITOR_PROMPT = """You translate editing instructions for a table of building observations into SQLite SQL.

Rules:
- Write ONE statement: an INSERT, an UPDATE or a DELETE, against the table named in TABLE
  and no other.
- Never DROP, ALTER, CREATE, ATTACH or PRAGMA, and never BEGIN, COMMIT or ROLLBACK: the
  caller owns the transaction.
- Never REPLACE INTO or INSERT OR REPLACE. Both delete the row they collide with, so a
  statement that reads as an addition would remove data nobody asked to remove.
- An UPDATE or a DELETE MUST carry a WHERE clause naming exactly the rows in the request.
  Without one it rewrites or empties the whole table.
- Pin a row down with everything the request gives you - the sensor AND the observed property
  AND the time - not with one of them. Filtering on a sensor alone hits every property it
  ever reported.
- The timestamp column holds a full ISO instant such as '2025-01-01T00:00:00Z'. A request
  that names a month or a year is a strftime comparison, or a LIKE, never an equality
  against a bare '2025-01'.
- An UPDATE or a DELETE must match existing literals exactly as VALUES spells them. A filter
  on a value that is not in that list matches no row at all.
- An INSERT is the one place a value outside VALUES belongs, because adding data is how a
  table gains one. When the request names a meter, a quantity or a unit the table has never
  held, COIN a new value in the style of the existing ones - same case, same word shape,
  same naming convention - rather than forcing the request into the nearest value that
  happens to be there already. Filing a new kind of reading under an old label corrupts
  every total that groups by it, and no later query can tell.
- An INSERT must fill every column listed in COLUMNS, in that order or by naming them. A row
  with no unit or no timestamp is invisible to every query that follows.
- Double-quote every column name containing ':' or a space, e.g. "sosa:madeBySensor".
- Reply with the statement and nothing else: no prose, no explanation, no markdown."""

    SQLITE_EDIT_REPAIR_PROMPT = """You fix SQLite INSERT, UPDATE and DELETE statements over a building observation table.

You are given the table description, the request, the statement, and the exact reason it was
rejected. Return a corrected single statement that writes only to the table named in TABLE.
Reply with the statement and nothing else: no prose, no explanation, no markdown."""

    # An update can name only real columns, compile cleanly, run without complaint and change
    # nothing at all, because its WHERE clause matched no row. The caller sees a table that is
    # simply unchanged, so the absence of a change has to be the signal.
    SQLITE_NO_CHANGE_REASON = (
        "The statement is valid but changed no rows: its WHERE clause matched nothing. Check "
        "every literal against the VALUES section, spelled exactly. Check the timestamp above "
        "all - the column holds a full ISO instant like '2025-01-01T00:00:00Z', so comparing it "
        "to '2025-01' or to a bare date matches nothing; use strftime or LIKE for a month. "
        "Rewrite the WHERE clause and try again."
    )

    @staticmethod
    def SQLiteWriteUpdate(
        llm: "ChatOpenAI",
        grounding: str,
        request: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Translate an editing instruction into a SQLite INSERT, UPDATE or DELETE.

        The statement is not checked here: SQL.ValidateUpdate decides whether it is usable.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The table description, from Observation.SQLiteSchemaSummary()['text'].
                It is the same block the query cycle is given: a table's columns and literals
                are all an edit needs too, where a graph edit needs vocabulary beyond the
                graph's own because a new node may carry a class the graph has never held.
            request: What to change, in natural language.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The proposed statement, fences stripped.

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
            Tool.SQLITE_EDITOR_PROMPT,
            f"TABLE DESCRIPTION\n{grounding}\n\nREQUEST\n{request.strip()}",
            meter,
            "agent 1 edit",
        ))

    @staticmethod
    def SQLiteRepairUpdate(
        llm: "ChatOpenAI",
        grounding: str,
        request: str,
        sql: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand an update back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The table description, as given to Tool.SQLiteWriteUpdate.
            request: The original instruction in natural language.
            sql: The statement that was rejected.
            reason: Why it was rejected: a safety refusal, SQLite's own compilation error, a
                failure to run, or SQLITE_NO_CHANGE_REASON.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: The corrected statement, fences stripped.

        Raises:
            ValueError: If inputs are missing.
            OSError:    If the provider could not be reached.
        """
        if not sql or not isinstance(sql, str):
            raise ValueError("sql must be a non-empty string.")
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string.")

        return _StripFences(LLM.Complete(
            llm,
            Tool.SQLITE_EDIT_REPAIR_PROMPT,
            f"TABLE DESCRIPTION\n{grounding}\n\nREQUEST\n{request.strip()}\n\n"
            f"REJECTED STATEMENT\n{sql}\n\nREASON\n{reason}",
            meter,
            "agent 2 repair",
        ))

    # =================================================================================
    # Tools of cycle 9 - a question answered from the graph AND the databases it points at
    # =================================================================================

    # What a twin question may need. 'graph' is answered from the triples alone, 'readings'
    # from the databases the graph locates, and 'both' needs a figure from each - the floor
    # area beside the kilowatt hours.
    TWIN_INTENTS = ("graph", "readings", "both")

    TWIN_ROUTER_PROMPT = """You route questions about a building twin.

A twin has two halves. The GRAPH holds what the estate IS: campuses, buildings, storeys,
spaces, their areas, heights and occupancies; where the measurements are kept, as documents;
and any figure that has already been WORKED OUT AND RECORDED on it, as KPIs. The DATABASES
hold what it DID: raw meter readings over time, one table per file.

Read the graph description and the question, then reply with ONE JSON object:
{"intent": "graph" | "readings" | "both"}

- "graph"    - everything asked for is already in the graph. How many spaces, how big, how
               many people, what is on which floor, which buildings exist - and ALSO any
               figure recorded there earlier. A question about something "on record",
               "recorded", "stored", or named as a KPI is asking for the graph to be read,
               not for the meters to be read again. When the CLASSES list carries a KPI
               class, such figures exist and the graph is where they are.
- "readings" - the answer has to be computed from raw measurements over time, and nothing
               already recorded covers it. How much was consumed, when did it peak, which
               meter is highest, how one month compared with another. The answer stays in
               the unit the meters record, and nothing is divided by anything.
- "both"     - the answer divides a raw measurement by an estate figure - per square metre,
               per m2, per person, per occupant, per storey, an "intensity", a "normalised"
               comparison - and the measurement still has to be totalled from the meters
               first. If that ratio is already recorded as a KPI, this is "graph".

A ratio wins over the other two. If the question asks for a measurement per something the
meters cannot know - an area, a head count, a number of storeys - answer "both" however much
the rest of it sounds like "readings". "Which building used the most electricity per square
metre" is "both", not "readings": the meters can total the kilowatt hours, but they have
never heard of a square metre.

Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    TWIN_LOCATOR_PROMPT = """You write SPARQL that finds which measurement databases a question needs.

The graph records each database as a document node hanging off the thing it measures, with a
property set giving its file path and how to read it. Your query must return one row per
database, projecting these variable names EXACTLY:

  ?filePath   - required. The path property of the database.
  ?owner      - the node the document hangs off, so a reading can be attributed to it.
  ?ownerLabel - that node's rdfs:label.
  ?sensor     - the sensor identifier stored with the database, when there is one.
  ?property   - what it measures, when the graph says.
  ?unit       - the unit, when the graph says.

A property is a NAME and a VALUE on two different predicates, so every variable above needs
its own block that pins the name and binds the value. This is the shape:

  ?owner btwin:hasDocument ?doc ; rdfs:label ?ownerLabel .
  ?doc ifc:HasPropertySets ?pset .
  ?pset ifc:HasProperties ?a . ?a rdfs:label "FilePath"         ; ifc:NominalValue ?filePath .
  ?pset ifc:HasProperties ?b . ?b rdfs:label "SensorID"         ; ifc:NominalValue ?sensor .
  ?pset ifc:HasProperties ?c . ?c rdfs:label "ObservedProperty" ; ifc:NominalValue ?property .
  ?pset ifc:HasProperties ?d . ?d rdfs:label "Unit"             ; ifc:NominalValue ?unit .

Read the property names you need out of the schema; the four above are the usual ones.

Rules:
- Use ONLY the prefixes, classes and predicates listed in the GRAPH SCHEMA. Invent nothing.
- Always include the PREFIX lines for every prefix you use.
- Give each property block its OWN variable, as ?a ?b ?c ?d above. One variable reused across
  several names binds nothing at all, because a single property cannot be labelled "FilePath"
  and "SensorID" at the same time.
- ?filePath must come from the property whose label is "FilePath". It is NOT the document's
  rdfs:label: that is a title such as "Administration - electricity readings 2025", and no
  file is called that. If your rows come back holding a title, you bound the wrong thing -
  add the property block above rather than filtering the title.
- Do not put the property NAME in the SELECT as if it were the value, and do not return one
  row per property: one row per DATABASE, with its six values side by side.
- SELECT exactly the variables above. ?filePath is the one that must always be bound.
- This query LOCATES databases; it does not read them. The graph holds no measurements, so
  do not aggregate, do not ORDER BY a reading, and do not add a property block for a name
  that is not in PROPERTY VALUES - a block that binds nothing empties the whole result.
  Return every database the question is about; the readings are fetched afterwards.
- Narrow to what the question asks for and no more. A question about one campus must not
  return the databases of another; a question about electricity must not return water. Filter
  on the label of the owner, of the document, or on the measured property.
- A question that names no particular building or utility wants ALL of them: do not invent a
  filter the question did not ask for.
- End with LIMIT {limit} or less.
- Reply with the query and nothing else: no prose, no explanation, no markdown."""

    TWIN_LOCATOR_REPAIR_PROMPT = """You fix SPARQL that finds measurement databases in a building twin.

You are given the schema, the question, the query, and the exact reason it was rejected.
Return a corrected SELECT that projects ?filePath and, where the graph has them, ?owner,
?ownerLabel, ?sensor, ?property and ?unit.

A property is a NAME and a VALUE on two different predicates, so each variable needs its own
block that pins the name and binds the value:

  ?owner btwin:hasDocument ?doc ; rdfs:label ?ownerLabel .
  ?doc ifc:HasPropertySets ?pset .
  ?pset ifc:HasProperties ?a . ?a rdfs:label "FilePath"         ; ifc:NominalValue ?filePath .
  ?pset ifc:HasProperties ?b . ?b rdfs:label "SensorID"         ; ifc:NominalValue ?sensor .
  ?pset ifc:HasProperties ?c . ?c rdfs:label "ObservedProperty" ; ifc:NominalValue ?property .
  ?pset ifc:HasProperties ?d . ?d rdfs:label "Unit"             ; ifc:NominalValue ?unit .

If the rejection says a bound path is not a file, the fix is almost always this: ?filePath was
taken from the document's rdfs:label instead of from the "FilePath" property. Bind it from the
property block, do not filter the label.
Reply with the query and nothing else: no prose, no explanation, no markdown."""

    TWIN_ANSWER_PROMPT = """You answer questions about a building using ONLY the data you are given.

You may be given two blocks. MEASUREMENTS are rows read from the twin's databases, each
tagged with the building it came from. ESTATE is what the graph records about those same
buildings - floor areas, occupancies, how many spaces.

- MEASUREMENTS arrive ONE ROW PER BUILDING, because each building's readings live in their
  own database and were read separately. Nothing has been added up for you. A question about
  a total across buildings, a campus or the site is answered by SUMMING those rows and giving
  the sum; listing the parts is not an answer to 'how much in total'. A question about a
  ranking is answered by ordering them.
- Use both blocks when the question needs both: consumption per square metre is a measurement
  divided by an estate figure, and you should show the division, not just its result.
- A per-unit figure REQUIRES the divisor to be in the ESTATE block. If a question asks for
  something per square metre, per person or per anything else and no ESTATE block is present,
  or it holds no such property, say that the estate figures were not retrieved and give the
  totals instead. Do NOT reach for a round number, a conversion factor, or a size you think
  a building of that kind has: an invented divisor produces a figure that looks exactly like
  a computed one and is wrong by whatever you guessed.
- Never introduce a number that is in neither block, and never estimate one.
- Quote figures with the unit they carry. An estate total is a sum over the spaces in a
  building, so summing a height or an area per person would be meaningless - use the totals
  only where a total is what the question wants.
- If the blocks are empty or do not cover the question, say so plainly.
- Be concise: four sentences at most, or a short list when the answer is a ranking."""

    # A locator can be legal, parse cleanly and return nothing, because it filtered on a label
    # that is not in the graph. That reads exactly like "this estate has no such database".
    TWIN_NO_DATABASE_REASON = (
        "The query is valid but matched no database. Check every literal you filtered on "
        "against the ENTITIES list, spelled exactly, and check that each property name you "
        "matched really appears in the graph. Remember the value of a property hangs off a "
        "property set, not off the document itself. Widen or correct the filter and try again."
    )

    @staticmethod
    def TwinRoute(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Decide whether a question needs the graph, the databases, or both.

        The one step that reads the question before anything has been retrieved, and the
        reason Cycle.TwinQueryByPrompt can be a single entry point: 'how many spaces are in
        the Library' and 'how much electricity did it use' are the same kind of question to a
        user and completely different pipelines underneath.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The graph schema as text, from RDF.SchemaSummary()['text'].
            question: The question in natural language.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: One of Tool.TWIN_INTENTS.

        Raises:
            ValueError: If `question` is missing.
            OSError:    If the provider could not be reached.
        """
        if not question or not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string.")

        # Labelled apart from the chat router and the edit router: all three route, and a
        # cost table that calls them the same thing cannot say which one a session spent on
        reply = LLM.Complete(
            llm,
            Tool.TWIN_ROUTER_PROMPT,
            f"GRAPH SCHEMA\n{grounding}\n\nQUESTION\n{question.strip()}",
            meter,
            "router half",
        )

        # A router that answers in prose, or invents a fourth intent, must not end the run.
        # 'both' is the safe default: it gathers the readings AND the estate figures, so the
        # answering agent has everything either of the narrower intents would have given it.
        try:
            parsed = json.loads(_ExtractJSON(reply))
        except (ValueError, TypeError):
            parsed = {}
        candidate = str((parsed or {}).get("intent") or "").strip().lower()
        return candidate if candidate in Tool.TWIN_INTENTS else "both"

    @staticmethod
    def TwinPropertyBlock(
        rdfGraph=None,
        valueLimit: int = 25,
        maxNames: int = 30,
    ) -> str:
        """
        The property names in the graph, and the literals each one actually holds. No model.

        RDF.SchemaSummary describes a graph's classes, predicates, shapes and node labels -
        everything except the one thing a locator has to filter on. A database is picked out
        by the VALUE of its ObservedProperty, and nothing in the schema says that value is
        spelled 'ElectricityConsumption' rather than 'electricity', so a model with only the
        schema in front of it has to guess a literal. A guessed literal parses, runs, and
        matches nothing, which reads exactly like an estate with no electricity meters.

        This is RDF's counterpart of the VALUES section of Observation.SQLiteSchemaSummary,
        and it follows the same rule: a property whose values are few and textual is
        vocabulary and gets listed, one whose values are many or numeric is a measurement and
        gets a range instead. Listing 84 floor areas would drown the block in the one thing a
        filter is never written against.

        Args:
            rdfGraph: An rdflib.Graph to read.
            valueLimit: Above this many distinct values, a property is summarised, not listed.
            maxNames: How many property names to describe.

        Returns:
            str: The block appended to the schema, or '' when the graph carries no properties.

        Raises:
            ImportError: If `rdflib` is not installed.
            ValueError:  If `rdfGraph` is None.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")

        rows = RDF.Query(rdfGraph, """
            PREFIX ifc: <https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?name ?value WHERE {
              ?p rdfs:label ?name ; ifc:NominalValue ?value .
            } LIMIT 5000""")
        if not rows:
            return ""

        values: Dict[str, List[str]] = {}
        for row in rows:
            name, value = row.get("name"), row.get("value")
            if name and value is not None and value not in values.setdefault(name, []):
                values[name].append(str(value))

        def numeric(items: List[str]) -> bool:
            """Whether every value parses as a number, so the property is a measurement."""
            for item in items:
                try:
                    float(item)
                except ValueError:
                    return False
            return bool(items)

        lines = ["PROPERTY VALUES (what the properties in this graph actually hold -",
                 "                 filter on these literals, spelled exactly)"]
        for name in sorted(values)[:maxNames]:
            found = values[name]
            if numeric(found):
                numbers = [float(v) for v in found]
                lines.append(f"  {name}: {len(found)} numeric value(s), "
                             f"{min(numbers):g} to {max(numbers):g}")
            elif len(found) <= valueLimit:
                lines.append(f"  {name}: " + ", ".join(repr(v) for v in sorted(found)))
            else:
                lines.append(f"  {name}: {len(found)} distinct value(s), e.g. "
                             + ", ".join(repr(v) for v in sorted(found)[:3]))
        return "\n".join(lines)

    @staticmethod
    def TwinWriteLocator(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        meter: Optional[CostMeter] = None,
        rowLimit: int = 100,
    ) -> str:
        """
        Write the SPARQL that finds which databases a question needs.

        The query is not checked here: SPARQL.Validate decides whether it parses and uses
        legal vocabulary, and Tool.TwinTargets decides whether its rows are usable.

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
            Tool.TWIN_LOCATOR_PROMPT.format(limit=rowLimit),
            f"GRAPH SCHEMA\n{grounding}\n\nQUESTION\n{question.strip()}",
            meter,
            "agent 1 locate",
        ))

    @staticmethod
    def TwinRepairLocator(
        llm: "ChatOpenAI",
        grounding: str,
        question: str,
        sparql: str,
        reason: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Hand a locator back to the model with the exact reason it was rejected.

        Args:
            llm: A chat model from LLM.Constructor.
            grounding: The graph schema as text, as given to Tool.TwinWriteLocator.
            question: The original question in natural language.
            sparql: The query that was rejected.
            reason: Why: a parse error, a missing ?filePath, no readable file, or
                TWIN_NO_DATABASE_REASON.
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
            Tool.TWIN_LOCATOR_REPAIR_PROMPT,
            f"GRAPH SCHEMA\n{grounding}\n\nQUESTION\n{question.strip()}\n\n"
            f"REJECTED QUERY\n{sparql}\n\nREASON\n{reason}",
            meter,
            "agent 2 repair",
        ))

    @staticmethod
    def TwinTargets(
        rows: Optional[List[Dict[str, Any]]] = None,
        basePath: Optional[Union[str, Path]] = None,
        maxDatabases: int = 25,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Turn the locator's rows into databases that can actually be opened. No model.

        This is where a query that looks right stops being taken on trust. The graph stores a
        path, not a file: it may be relative, it may name something that has been moved or
        never existed, and the same database may be returned twice by a query that joined one
        hop too many. Each row is resolved against `basePath`, checked on disk, and
        deduplicated by resolved path.

        Args:
            rows: The rows returned by RDF.Query for the locator.
            basePath: The directory the graph's paths are relative to. An absolute path in
                the graph is used as it stands.
            maxDatabases: Refuse a fan-out wider than this. A locator that dropped its filter
                would otherwise open every database in the estate and bill for it.

        Returns:
            tuple: (targets, "") when at least one file was found, or ([], the reason) when
                none was. Each target is
                {'path', 'owner', 'ownerLabel', 'sensor', 'property', 'unit', 'table'}.

        Raises:
            TypeError: If `rows` is not a list.
        """
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise TypeError("rows must be a list.")
        if not rows:
            return [], Tool.TWIN_NO_DATABASE_REASON

        base = Path(basePath) if basePath else Path.cwd()

        # The locator is told to project ?filePath; a query that bound nothing under that
        # name has answered a different question from the one it was asked
        pathKeys = [k for k in rows[0] if k.lower() in ("filepath", "path", "file")]
        if not pathKeys:
            return [], (
                "The query returned rows but bound no ?filePath, so there is no database to "
                "open. Project ?filePath, taken from the file-path property of the document's "
                "property set.")

        targets: List[Dict[str, Any]] = []
        missing: List[str] = []
        seen = set()

        def pick(row: Dict[str, Any], *names: str) -> Optional[str]:
            """First bound value among these variable names, matched case-insensitively."""
            for key, value in row.items():
                if str(key).lower() in names and value not in (None, ""):
                    return str(value)
            return None

        for row in rows:
            raw = pick(row, *[k.lower() for k in pathKeys])
            if not raw:
                continue
            resolved = Path(raw) if Path(raw).is_absolute() else base / raw
            resolved = resolved.resolve()
            if not resolved.is_file():
                if raw not in missing:
                    missing.append(raw)
                continue
            if str(resolved) in seen:
                continue
            seen.add(str(resolved))
            targets.append({
                "path": str(resolved),
                "owner": pick(row, "owner", "building", "node"),
                "ownerLabel": pick(row, "ownerlabel", "label", "name"),
                "sensor": pick(row, "sensor", "sensorid"),
                "property": pick(row, "property", "observedproperty", "measures"),
                "unit": pick(row, "unit"),
                "table": pick(row, "table", "tablename"),
            })

        if not targets:
            listed = ", ".join(repr(m) for m in missing[:5])
            # A value with no separator and no extension is a title, not a path, and that is
            # one specific mistake with one specific fix - worth saying so rather than
            # leaving the repair agent to guess which of its patterns was wrong
            looksLikeTitle = missing and not any(
                ("/" in m or "\\" in m or "." in m.rsplit("/", 1)[-1]) for m in missing)
            hint = (
                " Those are titles, not paths: ?filePath was bound to the document's "
                "rdfs:label. Bind it from the property whose rdfs:label is \"FilePath\", "
                "using its own property block."
                if looksLikeTitle else
                " Check that ?filePath is bound to the path property and not to a label "
                "or an IRI.")
            return [], (
                f"The query returned {len(rows)} row(s) but none named a file that is there. "
                f"Paths bound: {listed or '(none)'}. They are resolved against {base}.{hint}")

        if len(targets) > maxDatabases:
            return [], (
                f"The query selected {len(targets)} databases, over the limit of "
                f"{maxDatabases}. Narrow it to the ones the question actually asks about.")

        return targets, ""

    @staticmethod
    def TwinSQLBlock(targets: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Tell the SQL writer that its one query will be run against many databases.

        The fan-out is the thing that has to be said out loud. Each file holds one building's
        readings, so the query must NOT filter by building or by sensor - that selection has
        already happened, in the graph - and it must compute the same figure everywhere, or
        the numbers it returns will not be comparable across the buildings being ranked.

        Args:
            targets: The output of Tool.TwinTargets.

        Returns:
            str: The block appended to the table description, or '' when there are no targets.
        """
        targets = targets or []
        if not targets:
            return ""

        lines = [f"THIS QUERY RUNS AGAINST {len(targets)} SEPARATE DATABASE(S)",
                 "  All of them share the columns described above. One will be run per file:"]
        for target in targets[:12]:
            owner = target.get("ownerLabel") or "(unlabelled)"
            measured = target.get("property") or "?"
            lines.append(f"    {owner} - {measured} [{target.get('unit') or '?'}]")
        if len(targets) > 12:
            lines.append(f"    ... and {len(targets) - 12} more")
        lines.append(
            "  Each file holds ONE building's readings, and which files to open has already\n"
            "  been decided. Do NOT filter by building, by sensor or by measured property:\n"
            "  such a filter would match in one file and empty every other one.\n"
            "  Compute the SAME figure in every file, so the results can be compared. The\n"
            "  building each row came from is attached afterwards, so you do not need to\n"
            "  select it - and cannot, since no file knows its own building.\n"
            "  Return ONE ROW per file unless the question actually asks to see a series.\n"
            "  The fan-out already gives one result per building, so a query that also groups\n"
            "  by month returns twelve rows times every building opened - a table nobody\n"
            "  asked for, and one that buries the comparison being made. Group by time ONLY\n"
            "  for a question about a profile, a trend or a peak month.\n"
            "  Return RAW MEASURED TOTALS. These files hold readings and nothing else - no\n"
            "  floor area, no headcount, no building size of any kind - so a column named\n"
            "  'per_square_metre' or 'per_person' cannot be computed here and would only be a\n"
            "  guess wearing the name of a calculation. A per-unit figure is worked out\n"
            "  afterwards, from the estate figures the graph holds. Give the total; the\n"
            "  division is not yours to do.")
        return "\n".join(lines)

    @staticmethod
    def TwinEstateBlock(
        rdfGraph=None,
        targets: Optional[List[Dict[str, Any]]] = None,
        maxOwners: int = 12,
    ) -> str:
        """
        What the graph records about the buildings the readings came from. No model.

        This is the half that makes a 'per square metre' question answerable. The readings
        know nothing about size; the graph does, and the two meet here - every numeric
        property of everything located inside each owner, summed, beside the count of things
        it was summed over.

        Summing is right for an area and a headcount and wrong for a height, which is why the
        count is included and the answering prompt is told what a total means. Reporting the
        sum and letting the answer refuse it is better than guessing which properties are
        additive from their names.

        Args:
            rdfGraph: The rdflib.Graph the targets were located in.
            targets: The output of Tool.TwinTargets.
            maxOwners: How many owners to describe.

        Returns:
            str: The block shown to the answering agent, or '' when nothing was found.

        Raises:
            ImportError: If `rdflib` is not installed.
        """
        if rdfGraph is None or not targets:
            return ""

        owners: List[Tuple[str, str]] = []
        for target in targets:
            key = (target.get("owner") or "", target.get("ownerLabel") or "")
            if key[0] and key not in owners:
                owners.append(key)
        if not owners:
            return ""

        lines = ["ESTATE (what the graph records about those buildings)"]
        for owner, label in owners[:maxOwners]:
            # The same totals Tool.TwinKPIObjects divides by, from the same function. Two
            # implementations would eventually disagree, and the one place that would show is
            # a confirmation prompt quoting a divisor the arithmetic did not use.
            totals = Tool.TwinOwnerTotals(rdfGraph, owner)
            if not totals:
                continue
            things = totals.pop("", {}).get("things", 0)
            described = ", ".join(
                f"{name} total {entry['sum']:,.1f} {entry['unit'] or ''}".strip()
                + f" over {entry['n']}"
                for name, entry in sorted(totals.items()))
            lines.append(f"  {label or owner}: {things} space(s) - {described}")

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def TwinAnswer(
        llm: "ChatOpenAI",
        question: str,
        rows: Optional[List[Dict[str, Any]]] = None,
        estate: str = "",
        meter: Optional[CostMeter] = None,
        rowLimit: int = 100,
    ) -> str:
        """
        Word an answer from the retrieved readings and the estate figures beside them.

        Tool.SQLiteAnswer with a second block. Everything that applies there applies here:
        the answer may use these rows and nothing else. What is new is that the model is
        expected to do arithmetic ACROSS the two blocks - a total divided by a floor area -
        and is told to show the division rather than only its result, because a per-unit
        figure with no visible numerator cannot be checked against anything.

        Args:
            llm: A chat model from LLM.Constructor.
            question: The question in natural language.
            rows: The merged rows, each tagged with the building it came from.
            estate: The block from Tool.TwinEstateBlock, or '' when there is none.
            meter: Optional CostMeter to record tokens and cost into.
            rowLimit: How many rows to show the model.

        Returns:
            str: The natural-language answer.

        Raises:
            TypeError: If `rows` is not a list.
            OSError:   If the provider could not be reached.
        """
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise TypeError("rows must be a list.")

        if rows:
            rendered = "\n".join(
                "; ".join(f"{k}={v}" for k, v in row.items() if v is not None)
                for row in rows[:rowLimit])
        else:
            rendered = "(no readings were retrieved)"

        prompt = f"QUESTION\n{question.strip()}\n\nMEASUREMENTS\n{rendered}"
        if estate:
            prompt += f"\n\n{estate}"

        return LLM.Complete(llm, Tool.TWIN_ANSWER_PROMPT, prompt, meter, "answer")

    # =================================================================================
    # Tools of cycle 11 - changing a twin: its graph, its databases, or the graph FROM them
    # =================================================================================

    # The three things a request to change a twin can mean. The third is the one a twin is
    # for: it reads the databases and writes the graph, which neither half could do alone.
    TWIN_EDIT_INTENTS = ("graph", "readings", "derive")

    CHAT_TWIN_ROUTER_PROMPT = """You route the turns of a conversation about a building twin.

A twin is two things kept together. The GRAPH holds what the estate IS: campuses, buildings,
storeys, spaces, their areas and occupancies, and any figures already recorded on them. The
DATABASES hold what it DID: meter readings over time.

Read the conversation so far and the new message, then reply with ONE JSON object:
{"intent": "question" | "edit" | "talk", "request": "the message, rewritten to stand alone"}

Choose the intent:
- "question" - it asks for something either half already holds, or for a comparison between
  them. What is there, how big, how much was used, which is highest, what is it per square
  metre. Asking for a figure is a question no matter how much work the figure takes.
- "edit" - it asks for something to CHANGE or to be KEPT. Correct a reading, rename a space,
  add a room, delete a faulty month - and also: work something out and RECORD it, store it,
  save it as a KPI, write it onto the buildings. A request that ends in the figure being kept
  is an edit even though it begins by computing one.
- "talk" - anything else: a greeting, thanks, or a question about the conversation itself.

The line between the first two is what happens to the answer. "Which building uses the most
per square metre?" is a question. "Work out the use per square metre and record it on each
building" is an edit, because the graph is different afterwards.

Write the request:
- Resolve every pronoun and every ellipsis against the conversation, so that someone who has
  not read it can still act on the request.
- Carry forward the building, the quantity and the period the conversation has settled on.
- Keep any instruction to record, store or save: dropping it turns an edit into a question.
- Change nothing else. Keep the user's wording and their language.
- For "talk", repeat the message unchanged.

Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    TWIN_EDIT_ROUTER_PROMPT = """You route requests to change a building twin.

A twin has two halves. The GRAPH holds what the estate IS: campuses, buildings, storeys,
spaces, their areas and occupancies. The DATABASES hold what it DID: meter readings over time.

Read the request and reply with ONE JSON object:
{"intent": "graph" | "readings" | "derive"}

- "graph"    - it changes a fact about the estate itself. Rename a space, add a room, record
               a floor area, remove a building. Nothing is measured; the graph is edited.
- "readings" - it changes a measurement. Correct a misread meter, delete a faulty month, add
               a bill that arrived late. The databases are edited; the estate is unchanged.
- "derive"   - it asks for something to be COMPUTED from the readings and recorded on the
               estate. Work out annual consumption per building and store it, add an energy
               intensity KPI, rank the buildings and write the figure onto each. The
               databases are read and the graph is written.

The giveaway for "derive" is a request that names a figure to be worked out AND somewhere on
the estate to keep it. If it only asks what the figure is, it is not an edit at all.

Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    TWIN_KPI_PROMPT = """You plan the KPIs to be recorded on a building from measurements already retrieved.

You are given the request, and the rows a query returned - one row per building, each tagged
with the building it came from. You are also given the ESTATE figures the graph holds about
those same buildings, when there are any.

You do NOT compute anything. You say what should be recorded and where each number comes
from; the arithmetic is done afterwards, from the rows, so that no figure is ever one you
wrote down.

Reply with ONE JSON object:
{
  "setName": "a short name for the group of KPIs, e.g. 'Energy KPIs 2025'",
  "hasBeginning": "ISO instant the figures cover from, or null",
  "hasEnd": "ISO instant they cover to, or null",
  "kpis": [
    {"name": "AnnualElectricityUse",
     "column": "the column of the rows holding the number",
     "unit": "kWh",
     "divideBy": null},
    {"name": "ElectricityUseIntensity",
     "column": "the same column",
     "unit": "kWh/m2",
     "divideBy": "NetFloorArea"}
  ]
}

Rules:
- "column" must name a column that is actually in the rows. Pick the one holding the measured
  number, not the building tag.
- "divideBy" is null for a plain total. To record a per-unit figure, name the ESTATE property
  to divide by exactly as it is spelled there - "NetFloorArea", "OccupantCount" - and give a
  "unit" that shows the division, such as "kWh/m2" or "kWh/person".
- The division happens ONCE, afterwards, and you ask for it by naming "divideBy". So "column"
  must hold a RAW TOTAL. A column named as though it were already per square metre or per
  person is not a total - the databases hold no sizes and cannot have divided by one - and
  pairing it with "divideBy" would divide the same figure twice. Pick the column holding the
  plain measured sum, and pair each KPI with the divisor it needs.
- Name a KPI the way a building manager would read it: what it measures, over what period.
  No spaces, no units in the name; the unit has its own field.
- Record only what the request asks for. One KPI is a complete answer to a request for one.
- Reply with the JSON object and nothing else: no prose, no explanation, no markdown."""

    @staticmethod
    def TwinEditRoute(
        llm: "ChatOpenAI",
        request: str,
        meter: Optional[CostMeter] = None,
    ) -> str:
        """
        Decide which half of a twin a change is asking for - or whether it spans both.

        Args:
            llm: A chat model from LLM.Constructor.
            request: What to change, in natural language, already standing on its own.
            meter: Optional CostMeter to record tokens and cost into.

        Returns:
            str: One of Tool.TWIN_EDIT_INTENTS.

        Raises:
            ValueError: If `request` is missing.
            OSError:    If the provider could not be reached.
        """
        if not request or not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string.")

        reply = LLM.Complete(
            llm, Tool.TWIN_EDIT_ROUTER_PROMPT, f"REQUEST\n{request.strip()}", meter,
            "router edit")

        # 'graph' is the safe default, not 'derive': it is the one path where the model has to
        # write an explicit update that a validator then holds to a single INSERT or DELETE,
        # so a misrouted request is refused rather than quietly writing computed numbers.
        try:
            parsed = json.loads(_ExtractJSON(reply))
        except (ValueError, TypeError):
            parsed = {}
        candidate = str((parsed or {}).get("intent") or "").strip().lower()
        return candidate if candidate in Tool.TWIN_EDIT_INTENTS else "graph"

    @staticmethod
    def TwinOwnerTotals(rdfGraph=None, owner: Optional[str] = None) -> Dict[str, Any]:
        """
        Every numeric property of everything located inside one node, summed. No model.

        The graph's half of a per-unit figure. A building carries no floor area of its own -
        its spaces do - so 'per square metre' means summing the spaces, and this is the one
        place that sum is computed. Tool.TwinEstateBlock renders it for a model to read;
        Tool.TwinKPIObjects divides by it to make a number no model ever touched.

        Args:
            rdfGraph: An rdflib.Graph to read.
            owner: The IRI of the node to total under, as a string.

        Returns:
            dict: {propertyName: {'sum': float, 'n': int, 'unit': str}} and a 'things' count
                under the reserved key '' - the number of distinct nodes summed over, which is
                what tells a total apart from a single reading.

        Raises:
            ImportError: If `rdflib` is not installed.
        """
        if rdfGraph is None or not owner:
            return {}

        rows = RDF.Query(rdfGraph, f"""
            PREFIX brick: <https://brickschema.org/schema/Brick#>
            PREFIX ifc: <https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?name ?value ?unit ?thing WHERE {{
              ?thing brick:hasLocation* <{owner}> .
              ?thing ifc:HasPropertySets ?pset . ?pset ifc:HasProperties ?p .
              ?p rdfs:label ?name ; ifc:NominalValue ?value .
              OPTIONAL {{ ?p ifc:Unit ?unit }}
            }} LIMIT 1000""")

        totals: Dict[str, Any] = {}
        things = set()
        for row in rows:
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue          # a text property has no total; it is not estate size
            things.add(row["thing"])
            entry = totals.setdefault(row["name"], {"sum": 0.0, "n": 0, "unit": row["unit"]})
            entry["sum"] += value
            entry["n"] += 1
        if totals:
            totals[""] = {"things": len(things)}
        return totals

    @staticmethod
    def TwinKPIPlan(
        llm: "ChatOpenAI",
        request: str,
        rows: Optional[List[Dict[str, Any]]] = None,
        estate: str = "",
        meter: Optional[CostMeter] = None,
        rowLimit: int = 60,
    ) -> Dict[str, Any]:
        """
        Decide what to record, and where each number comes from. The model computes nothing.

        This is the division of labour that makes a derived KPI trustworthy. The model reads
        the request and the shape of the rows and says 'record the column named total as
        AnnualElectricityUse in kWh, and record it again divided by NetFloorArea as
        ElectricityUseIntensity in kWh/m2'. Tool.TwinKPIObjects then does the reading and the
        dividing, in Python, from the rows the databases returned. A figure written into the
        graph is therefore never a figure a model wrote down - only a figure it named.

        Args:
            llm: A chat model from LLM.Constructor.
            request: What to record, in natural language.
            rows: The rows retrieved, each tagged with its building.
            estate: The block from Tool.TwinEstateBlock, naming what may be divided by.
            meter: Optional CostMeter to record tokens and cost into.
            rowLimit: How many rows to show the model.

        Returns:
            dict: {'setName', 'hasBeginning', 'hasEnd', 'kpis': [{'name', 'column', 'unit',
                'divideBy'}]}. 'kpis' is [] when the reply could not be read, which the caller
                must treat as 'nothing to record' rather than as a failure to retry.

        Raises:
            ValueError: If `request` is missing.
            OSError:    If the provider could not be reached.
        """
        if not request or not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string.")
        rows = rows or []

        rendered = "\n".join(
            "; ".join(f"{k}={v}" for k, v in row.items() if v is not None)
            for row in rows[:rowLimit]) or "(no rows were retrieved)"
        prompt = f"REQUEST\n{request.strip()}\n\nROWS\n{rendered}"
        if estate:
            prompt += f"\n\n{estate}"

        reply = LLM.Complete(llm, Tool.TWIN_KPI_PROMPT, prompt, meter, "agent 5 plan")

        try:
            parsed = json.loads(_ExtractJSON(reply))
        except (ValueError, TypeError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}

        kpis = []
        for entry in (parsed.get("kpis") or []):
            if not isinstance(entry, dict):
                continue
            name, column = entry.get("name"), entry.get("column")
            if not (isinstance(name, str) and name.strip()):
                continue
            if not (isinstance(column, str) and column.strip()):
                continue
            kpis.append({
                "name": name.strip(),
                "column": column.strip(),
                "unit": (entry.get("unit") or "").strip() or None,
                "divideBy": (entry.get("divideBy") or None),
            })

        return {
            "setName": (parsed.get("setName") or "Derived KPIs").strip(),
            "hasBeginning": parsed.get("hasBeginning") or None,
            "hasEnd": parsed.get("hasEnd") or None,
            "kpis": kpis,
        }

    @staticmethod
    def TwinKPIObjects(
        rdfGraph=None,
        targets: Optional[List[Dict[str, Any]]] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
        plan: Optional[Dict[str, Any]] = None,
        baseIRI: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """
        Build the KPI nodes a plan describes, doing every sum and division here. No model.

        The numbers come out of `rows`, which came out of the databases; the divisors come out
        of the graph through Tool.TwinOwnerTotals. Nothing here is parsed out of a model's
        prose, so a KPI that lands in the graph is arithmetic on retrieved data and can be
        recomputed by hand from the same two places.

        A KPI is skipped rather than guessed when its column is missing from a building's
        rows, or when the property it divides by is not recorded for that building. Half a
        ranking is better than a ranking with an invented number in it, and what was skipped
        is returned so the caller can say so.

        Args:
            rdfGraph: The graph the buildings live in, read for the divisors.
            targets: The output of Tool.TwinTargets, mapping buildings to their databases.
            rows: The rows retrieved, each tagged with its building.
            plan: The output of Tool.TwinKPIPlan.
            baseIRI: The base the graph's identifiers were minted with. Supplied so each
                proposed KPI can say whether recording it would REPLACE one already in the
                graph - which a user has to be told before agreeing, not after.

        Returns:
            tuple: (objects, proposed, reason). `objects` are the KPISet and KPI dictionaries
                to serialize, `proposed` is one flat record per KPI for showing to a user
                before anything lands - including 'replaces', True when a KPI of that name is
                already recorded on that building - and `reason` is why nothing was built.

        Raises:
            ImportError: If `rdflib` is not installed.
        """
        targets, rows = targets or [], rows or []
        plan = plan or {}
        if not plan.get("kpis"):
            return [], [], "The plan named no KPI to record."
        if not rows:
            return [], [], "No readings were retrieved, so there is nothing to compute from."

        # building label -> the node that owns it, so a KPI can be hung where it belongs
        owners: Dict[str, str] = {}
        for target in targets:
            label = target.get("ownerLabel") or target.get("owner")
            if label and target.get("owner"):
                owners.setdefault(label, target["owner"])

        objects: List[Dict[str, Any]] = []
        proposed: List[Dict[str, Any]] = []
        skipped: List[str] = []

        for label, owner in owners.items():
            mine = [r for r in rows if str(r.get("building")) == label]
            if not mine:
                continue
            totals = Tool.TwinOwnerTotals(rdfGraph, owner)

            setUID = f"{_SafeUID(label, 'building')}-{_SafeUID(plan['setName'], 'kpis')}"
            kpiSet = KPISet.Constructor(setUID, plan["setName"],
                                        hasBeginning=plan.get("hasBeginning"),
                                        hasEnd=plan.get("hasEnd"))
            KPISet.SetAssociatedObject(kpiSet, linkedObjectUID=owner,
                                       linkedObjectType="bot:Building")
            built = 0

            for entry in plan["kpis"]:
                raw = next((r.get(entry["column"]) for r in mine
                            if r.get(entry["column"]) is not None), None)
                if raw is None:
                    skipped.append(f"{label}/{entry['name']}: no column {entry['column']!r}")
                    continue
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    skipped.append(f"{label}/{entry['name']}: {raw!r} is not a number")
                    continue

                divisor = entry.get("divideBy")
                if divisor:
                    total = totals.get(divisor)
                    if not total or not total["sum"]:
                        skipped.append(f"{label}/{entry['name']}: the graph records no "
                                       f"{divisor} to divide by")
                        continue
                    value = value / total["sum"]

                kpiUID = f"{setUID}-{_SafeUID(entry['name'], 'kpi')}"
                KPISet.SetKPI(kpiSet, KPI.Constructor(
                    kpiUID, entry["name"], round(value, 4), kpiUnit=entry["unit"]))

                # The UID is derived from the building and the KPI name, so recording the
                # same KPI twice targets the same node. That is what makes an update an
                # update rather than a duplicate - and what makes it worth saying out loud
                # before it happens.
                existing = None
                if rdfGraph is not None:
                    existing = Tool.TwinRecordedValue(
                        rdfGraph, _MintIRI(baseIRI, kpiUID))

                proposed.append({
                    "building": label, "owner": owner, "kpi": entry["name"],
                    "value": round(value, 4), "unit": entry["unit"],
                    "from": entry["column"],
                    "dividedBy": f"{divisor}={totals[divisor]['sum']:g}" if divisor else "",
                    "replaces": existing,
                })
                built += 1

            if built:
                objects.append(kpiSet)

        if not objects:
            return [], [], ("Nothing could be computed: "
                            + ("; ".join(skipped[:4]) if skipped else "no building matched."))
        return objects, proposed, "; ".join(skipped[:4])

    @staticmethod
    def TwinRecordedValue(rdfGraph=None, iri: Optional[str] = None) -> Optional[str]:
        """
        The value already recorded on a node, when there is one. No model.

        Args:
            rdfGraph: An rdflib.Graph to look in.
            iri: The absolute IRI of the node, from _MintIRI.

        Returns:
            str | None: The existing nominal value as a string, or None when the node carries
                none - which is also the answer for a node that is not in the graph at all.

        Raises:
            ImportError: If `rdflib` is not installed.
        """
        try:
            from rdflib import URIRef
        except Exception as exc:
            raise ImportError("rdflib is required. Install with `pip install rdflib`.") from exc

        if rdfGraph is None or not iri:
            return None
        nominal = URIRef(Serialization.IRIs()["prefixes"]["ifc"] + "NominalValue")
        found = rdfGraph.value(URIRef(iri), nominal)
        return None if found is None else str(found)

    @staticmethod
    def TwinApplyObjects(rdfGraph=None, objects: Optional[List[Dict[str, Any]]] = None,
                         baseIRI: Optional[str] = None,
                         replace: bool = True) -> Tuple[int, str]:
        """
        Serialize BTwin objects to triples and merge them into a graph in place. No model.

        The write half of a derived edit, and deliberately the dullest part of it: the objects
        were built by the library, so this is the ordinary JSON-LD path, not a model-authored
        SPARQL update. There is nothing here for a validator to catch because there was never
        an opportunity for the model to write a triple.

        `replace` is what makes recording a KPI twice an UPDATE rather than a corruption. RDF
        adds, it does not overwrite: a KPI node whose value is recomputed from a fresh month
        of readings would otherwise end up carrying both figures at once, and every query
        would get two rows with no way to tell which is current. So every subject about to be
        written is cleared first, along with one level of blank nodes hanging off it - an old
        evaluation interval would otherwise survive its KPI set as unreachable garbage.

        Args:
            rdfGraph: The graph to merge into. Edited in place.
            objects: KPISet or other BTwin dictionaries.
            baseIRI: The base the graph's own identifiers were minted with, so a KPI set
                lands beside the building it names rather than in a namespace of its own.
            replace: Clear each incoming subject before writing it. False appends instead,
                which is right only when the subjects are known to be new.

        Returns:
            tuple: (net change in triples, "") on success, or (0, the reason) when nothing
                was added. The count is a NET change: replacing a KPI with another of the
                same shape moves no triples at all and correctly reports 0.

        Raises:
            ImportError: If `rdflib` is not installed.
        """
        try:
            from rdflib import BNode, URIRef
        except Exception as exc:
            raise ImportError("rdflib is required. Install with `pip install rdflib`.") from exc

        if rdfGraph is None or not objects:
            return 0, "Nothing to add."
        try:
            # strictValidation off: a KPISet names the building it belongs to, and that
            # building is in the graph already rather than in this handful of new objects
            jsonld = Serialization.JSONLDByObjects(objects, strictValidation=False)
            added, turtle = RDF.ByJSONLD(jsonld=jsonld, baseIRI=baseIRI)
        except (ValueError, TypeError, KeyError) as exc:
            return 0, f"The objects could not be serialized: {exc}"

        # RDF.ByJSONLD mints absolute IRIs for '@id' values but leaves the context's own
        # prefixes as the context declares them, and BTwin declares btwin: as the relative
        # 'btwin#'. Merged straight in, a KPI set would be typed 'btwin#KPISet' beside the
        # host graph's 'https://.../btwin#Document' - two namespaces spelled the same, and
        # RDF.SchemaSummary would offer the model 'btwin#KPISet' as a class name. That is not
        # a legal CURIE, so the next question written against it does not parse.
        #
        # Re-reading the Turtle with the base resolves them, which is exactly what RDF.ByTTL
        # does and why a graph that has been through a file never shows this.
        if baseIRI:
            try:
                from rdflib import Graph as RDFGraph
                resolved = RDFGraph()
                resolved.parse(data=turtle, format="turtle", publicID=baseIRI)
                added = resolved
            except Exception as exc:
                return 0, f"The objects could not be resolved against {baseIRI}: {exc}"

        before = len(rdfGraph)

        if replace:
            incoming = {s for s in set(added.subjects()) if isinstance(s, URIRef)}
            stale = [triple for triple in rdfGraph if triple[0] in incoming]
            orphans = {o for _s, _p, o in stale if isinstance(o, BNode)}
            for triple in stale:
                rdfGraph.remove(triple)
            for orphan in orphans:
                rdfGraph.remove((orphan, None, None))
        # Bindings before triples. '+=' merges the statements and leaves the prefixes behind,
        # so eko:KPI would arrive in the graph as an anonymous ns1:KPI - readable to rdflib,
        # unreadable to the next question, whose grounding block is built by compacting these
        # very IRIs and which would then teach the model a prefix that changes every session.
        existing = {prefix for prefix, _ in rdfGraph.namespaces()}
        for prefix, namespace in added.namespaces():
            if prefix and prefix not in existing:
                rdfGraph.bind(prefix, namespace)
        rdfGraph += added
        return len(rdfGraph) - before, ""


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
        chains: Optional[List[Dict[str, Any]]] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Answer a natural-language question about an RDF graph, through a hosted LLM.

        A Graph-RAG pipeline of five steps, only three of which call a model:
        1. RDF.Index and 2. RDF.SchemaSummary describe the graph, and RDF.Chains spells out the
           multi-hop paths through it (no model);
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
            chains: The output of RDF.Chains, reused across questions when supplied. Computed
                here when not, and both describe the graph as it is now: pass fresh ones after
                an edit. Pass [] to ground the writer on the schema alone.
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
        if chains is None:
            chains = RDF.Chains(rdfGraph)
        meter = meter if meter is not None else CostMeter()

        # The schema, then the paths through it. Both agents that write a query are given the
        # same grounding: a repair that could not see the chains would be asked to fix a join
        # it was never shown the shape of.
        block = Tool.RDFChainBlock(chains)
        grounding = f"{schema['text']}\n\n{block}" if block else schema["text"]

        # Where this question's calls start, so its cost can be split out of the run total
        first = len(meter.calls)

        sparql = Tool.RDFWriteSPARQL(llm, grounding, prompt, meter, rowLimit)
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
            previous = sparql
            sparql = Tool.RDFRepairSPARQL(llm, grounding, prompt, sparql, error, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 4] repaired query:\n{sparql}")
            if sparql.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempts} attempt(s): the model returned the query "
                    f"it was just asked to fix, so further retries would be identical. Raise "
                    f"`temperature` on the LLM so retries can differ, or rephrase the question. "
                    f"Last error: {error}")

        if verbose:
            print("[agent 4] accepted")

        rows = RDF.Query(rdfGraph, sparql)
        if verbose:
            print(f"[agent 5] {len(rows)} row(s), no model call")

        # An empty SELECT is the one failure the validator cannot see: legal vocabulary,
        # clean parse, wrong path. Give it back to the repair chain, but keep the rewrite
        # only if it actually finds something - otherwise the original query stands and the
        # empty answer is real. ASK is left alone: false is an answer, not a miss.
        # 'Empty' here is _NoMatch rather than `not rows`, because an aggregate over a
        # pattern that joined to nothing still returns a row, and it returns zeros.
        for retry in range(emptyRetries):
            if not _NoMatch(rows) or SPARQL.Form(sparql) != "SELECT":
                break
            if verbose:
                print(f"[agent 4] empty result, asking for a rewrite ({retry + 1}/{emptyRetries})")

            candidate = Tool.RDFRepairSPARQL(
                llm, grounding, prompt, sparql, Tool.RDF_EMPTY_RESULT_REASON, meter)
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
            if not _NoMatch(candidateRows):
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

            previous = document
            document = Tool.JSONLDRepair(
                llm, vocabularyText, notationText, prompt, document, error, meter)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")
            if document.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempts} attempt(s): the model returned the "
                    f"document it was just asked to fix, so further retries would be identical. "
                    f"Raise `temperature` on the LLM so retries can differ, or reword the "
                    f"prompt. Last error: {error}")

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

            previous = reply
            reply = Tool.JSONLDEditRepair(
                llm, vocabularyText, documentText, prompt, reply, error, meter)
            if reply.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempts} attempt(s): the model returned the patch "
                    f"it was just asked to fix, so further retries would be identical. Raise "
                    f"`temperature` on the LLM so retries can differ, or reword the request. "
                    f"Last error: {error}")
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
            previous = sparql
            sparql = Tool.RDFRepairUpdate(llm, grounding, prompt, sparql, error, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 4] repaired update:\n{sparql}")
            if sparql.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempts} attempt(s): the model returned the update "
                    f"it was just asked to fix, so further retries would be identical. Raise "
                    f"`temperature` on the LLM so retries can differ, or phrase the request as "
                    f"something expressible in one operation. Last error: {error}")

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

    @staticmethod
    def RDFChatTurn(
        rdfGraph=None,
        message: Optional[str] = None,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        chains: Optional[List[Dict[str, Any]]] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        confirm: Optional[Callable[[Dict[str, Any]], bool]] = None,
        maxTurns: int = 8,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Take one turn of a conversation about an RDF graph.

        The orchestration this and Cycle.RDFChat exist for: Tool.ChatRoute reads the
        conversation and turns the message into a self-contained request with an intent, and
        that request goes to Cycle.RDFQueryByPrompt to be answered or Cycle.RDFEditByPrompt to
        be applied. Neither of those two knows a conversation is happening - the memory is
        spent entirely on the rewrite, so an answer is still written from retrieved rows and
        nothing else.

        Nothing is read from or written to a terminal here, and the graph does not move on its
        own: an edit runs against a copy, and `confirm` decides whether the caller's graph
        follows. Cycle.RDFChat supplies a `confirm` that prints the diff and asks; another
        caller can pass `lambda proposal: True` to apply every edit, or leave it None to see
        what an edit would do without doing it.

        The turn is stateless. `history` is not modified: the returned dict carries a new list
        with this turn appended, and the caller passes it back for the next one.

        Args:
            rdfGraph: An rdflib.Graph to answer from and, when an edit is confirmed, to edit.
            message: What the user just typed, ellipsis and pronouns and all.
            history: Turns from the previous calls, as returned in 'history'.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary. Computed here when not supplied, and
                recomputed after a confirmed edit - it describes the graph as it was, so the
                next question would otherwise be grounded in a vocabulary that has moved.
            chains: The output of RDF.Chains, handled exactly as `schema` is: an edit that adds
                a relationship adds a path through it, which the next question should see.
            vocabulary: The output of Tool.JSONLDVocabulary, used by the edit path.
            meter: A CostMeter to tally token usage and cost into.
            confirm: Called with the proposed edit before the caller's graph is touched, and
                the edit is applied only if it returns True. None never applies.
            maxTurns: How many past turns the router is shown.
            maxRepairs: How many times a rejected query or update may be sent back.
            emptyRetries: How many times an empty result or a no-op update is rewritten.
            rowLimit: Maximum rows a generated SELECT may return.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'answer': str,        # what to show the user
                'intent': str,        # 'question', 'edit' or 'talk'
                'request': str,       # the message, restated to stand alone
                'sparql': str,        # the query or update, '' for a 'talk' turn
                'rows': list[dict],   # rows retrieved, for a question
                'source': list[str],  # graph nodes the answer is grounded in
                'added': list,        # triples an edit proposed adding, as strings
                'removed': list,      # triples an edit proposed removing
                'applied': bool,      # whether the edit reached rdfGraph
                'error': str | None,  # why a question or edit could not be served
                'history': list,      # `history` with this turn appended
                'schema': dict,       # the schema to pass to the next turn
                'chains': list,       # the chains to pass to the next turn
                'usage': dict,        # tokens and cost for this turn
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If inputs are missing.
            OSError:     If the model provider could not be reached. A conversation cannot
                continue through this, so it is left to reach the caller.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")
        if not message or not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")
        if history is not None and not isinstance(history, list):
            raise TypeError("history must be a list.")
        if confirm is not None and not callable(confirm):
            raise TypeError("confirm must be callable.")

        history = list(history or [])
        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = RDF.SchemaSummary(rdfGraph)
        if chains is None:
            chains = RDF.Chains(rdfGraph)
        meter = meter if meter is not None else CostMeter()

        # Where this turn's calls start, so its cost can be split out of the run total
        first = len(meter.calls)

        routed = Tool.ChatRoute(
            llm, Tool.ChatTranscript(history, maxTurns), message, meter)
        intent, request = routed["intent"], routed["request"]
        if verbose:
            print(f"\n[router]  {CostMeter.Describe(meter.calls[-1])}")
            print(f"[router]  {intent}: {request}")

        answer, sparql, error = "", "", None
        rows: List[Dict[str, Any]] = []
        source: List[str] = []
        added: List[Any] = []
        removed: List[Any] = []
        applied = False

        if intent == "talk":
            answer = Tool.ChatReply(
                llm, Tool.ChatTranscript(history, maxTurns), message, meter)
            if verbose:
                print(f"[talk]    {CostMeter.Describe(meter.calls[-1])}")

        elif intent == "edit":
            # A rejected update or an unfixable one ends this turn, not the conversation: the
            # user is told and can rephrase. Only OSError, the model being unreachable, gets
            # to end the session, and that is left to propagate.
            try:
                result = Cycle.RDFEditByPrompt(
                    rdfGraph, request, llm=llm, schema=schema, vocabulary=vocabulary,
                    meter=meter, maxRepairs=maxRepairs, emptyRetries=emptyRetries,
                    inPlace=False, verbose=verbose,
                )
            except ValueError as exc:
                error = str(exc)
                answer = f"I could not make that change: {exc}"
            else:
                sparql, added, removed = result["sparql"], result["added"], result["removed"]
                if not added and not removed:
                    answer = ("That change would leave the graph exactly as it is: nothing in "
                              "it matches what you described.")
                elif confirm is not None and confirm({
                    "request": request, "sparql": sparql,
                    "added": added, "removed": removed,
                }):
                    # RDFEditByPrompt renders the diff as compact strings to be read, not as
                    # triples to be replayed, and it ran against a copy. Diffing the two graphs
                    # recovers the triples themselves, so the caller's own graph moves rather
                    # than being swapped for the copy - anything else holding a reference to it
                    # would otherwise be left looking at the data from before the edit.
                    edited = result["graph"]
                    toRemove = set(rdfGraph) - set(edited)
                    toAdd = set(edited) - set(rdfGraph)
                    for triple in toRemove:
                        rdfGraph.remove(triple)
                    for triple in toAdd:
                        rdfGraph.add(triple)
                    applied = True
                    # The graph has moved, so what describes it is now the old description
                    schema = RDF.SchemaSummary(rdfGraph)
                    chains = RDF.Chains(rdfGraph)
                    answer = (f"Done: {len(added)} triple(s) added, {len(removed)} removed. "
                              f"The graph now holds {len(rdfGraph)} triples.")
                else:
                    answer = ("Left the graph as it was. The change is described above if you "
                              "want to ask for it differently.")

        else:
            try:
                result = Cycle.RDFQueryByPrompt(
                    rdfGraph, request, llm=llm, schema=schema, chains=chains, meter=meter,
                    maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                    verbose=verbose,
                )
            except ValueError as exc:
                error = str(exc)
                answer = f"I could not answer that: {exc}"
            else:
                answer, sparql = result["answer"], result["sparql"]
                rows, source = result["rows"], result["source"]

        turn = {"message": message.strip(), "intent": intent, "request": request,
                "answer": answer, "sparql": sparql, "applied": applied}

        return {
            "answer": answer,
            "intent": intent,
            "request": request,
            "sparql": sparql,
            "rows": rows,
            "source": source,
            "added": added,
            "removed": removed,
            "applied": applied,
            "error": error,
            "history": history + [turn],
            "schema": schema,
            "chains": chains,
            "usage": meter.Total(first),
        }

    @staticmethod
    def RDFChat(
        rdfGraph=None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        chains: Optional[List[Dict[str, Any]]] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        savePath: Optional[Union[str, Path]] = None,
        autoSave: bool = True,
        maxTurns: int = 8,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        silent: bool = False,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Hold a conversation about an RDF graph at the terminal.

        A loop around Cycle.RDFChatTurn, and the only thing in this module that reads a
        keyboard: it prints the answers, asks before an edit lands, and keeps the history and
        the schema threaded from one turn to the next. Everything it knows about buildings it
        gets from that one call.

        Every turn shows the query it was answered from and what it cost, because the reading
        that catches a wrong answer here is the query, not the sentence: a backwards triple
        pattern is valid, cheap and confidently empty. `silent` turns that off for a session
        that only wants the answers.

        Escape leaves at the prompt, as do /exit, Ctrl-C and end of input. At the confirmation
        of an edit it means no - refusing a change is not a reason to end the conversation.

        The commands, typed at the prompt:

            /help      what can be typed here
            /sparql    the query or update behind the last answer
            /history   the conversation as the router sees it
            /schema    the grounding block the model is given
            /cost      what the conversation has cost so far
            /silent    stop showing the query and the cost of each turn, or show them again
            /verbose   show each agent's step and cost, or stop showing them
            /save      write the graph to `savePath` as Turtle, when autoSave has not
            /exit      leave, /quit does the same

        Args:
            rdfGraph: An rdflib.Graph to talk about. Confirmed edits are applied to it.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary. Computed here when not supplied, and kept
                current across edits.
            chains: The output of RDF.Chains, kept current the same way.
            vocabulary: The output of Tool.JSONLDVocabulary, used by the edit path. Built once
                here, since an edit turn would otherwise rebuild it every time.
            meter: A CostMeter to tally token usage and cost into.
            savePath: Where the edited graph is written. This must not be the file the graph
                was read from: an edit is the model's work, and overwriting the source would
                leave nothing to compare it against. Without a path, nothing is ever written
                and an edited graph lives only as long as the session.
            autoSave: Write `savePath` as soon as an edit is applied, rather than waiting for
                /save. On by default, so a session cannot end with confirmed edits lost to a
                forgotten command. The file is written only once an edit lands, so a session
                that only asks questions leaves nothing behind.
            maxTurns: How many past turns the router is shown.
            maxRepairs: How many times a rejected query or update may be sent back.
            emptyRetries: How many times an empty result or a no-op update is rewritten.
            rowLimit: Maximum rows a generated SELECT may return.
            silent: Print the answers and nothing else - no query behind each turn, no running
                cost, no closing total. /silent toggles it.
            verbose: Start with the per-agent narration on. /verbose toggles it.

        Returns:
            dict: {
                'history': list,   # every turn taken
                'graph': Graph,    # the graph, edited in place where edits were confirmed
                'schema': dict,    # the schema as it stands at the end
                'chains': list,    # the chains as they stand at the end
                'edits': int,      # how many edits were applied
                'saved': bool,     # whether the graph on disk matches the graph in memory
                'usage': dict,     # tokens and cost for the whole conversation
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If `rdfGraph` is missing.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")

        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = RDF.SchemaSummary(rdfGraph)
        if chains is None:
            chains = RDF.Chains(rdfGraph)
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()
        meter = meter if meter is not None else CostMeter()

        history: List[Dict[str, Any]] = []
        lastResult: Optional[Dict[str, Any]] = None
        edits, unsaved = 0, False

        def confirm(proposal: Dict[str, Any]) -> bool:
            """Show the diff and ask. A model-written update is not applied unseen."""
            print("\n  the change it proposes:")
            for triple in proposal["removed"]:
                print(f"    - {' '.join(triple)}")
            for triple in proposal["added"]:
                print(f"    + {' '.join(triple)}")
            try:
                reply = _ReadLine("  apply? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                # Ctrl-C at the confirmation refuses the edit; it does not end the session
                print()
                return False
            # Escape here is the same answer as anything that is not yes: leave the graph alone
            return reply is not None and reply.strip().lower() in ("y", "yes")

        print(f"\nChatting about a graph of {len(rdfGraph)} triples, via {llm.model_name}.")
        print("Ask a question, or describe a change. /help for commands, Esc or /exit to leave.\n")

        while True:
            try:
                line = _ReadLine("you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line is None:            # Escape
                break
            message = line.strip()
            if not message:
                continue

            if message.startswith("/"):
                command = message.split()[0].lower()
                if command in ("/exit", "/quit"):
                    break
                elif command == "/help":
                    print("  /sparql  /history  /schema  /cost  /silent  /verbose  /save  /exit")
                    print("  Esc leaves too, and answers no to an edit.")
                elif command == "/sparql":
                    print(f"\n{lastResult['sparql'] or '(no query behind that answer)'}\n"
                          if lastResult else "  nothing asked yet")
                elif command == "/history":
                    print(f"\n{Tool.ChatTranscript(history, maxTurns)}\n")
                elif command == "/schema":
                    print(f"\n{schema['text']}\n")
                    print(f"{Tool.RDFChainBlock(chains) or '(no multi-hop chains)'}\n")
                elif command == "/cost":
                    total = meter.Total()
                    print(f"  {total['calls']} call(s), {CostMeter.Describe(total)}")
                elif command == "/silent":
                    silent = not silent
                    print(f"  silent {'on' if silent else 'off'}")
                elif command == "/verbose":
                    verbose = not verbose
                    print(f"  verbose {'on' if verbose else 'off'}")
                elif command == "/save":
                    if savePath is None:
                        print("  no savePath was given, so there is nowhere to write")
                    else:
                        rdfGraph.serialize(destination=str(savePath), format="turtle")
                        unsaved = False
                        print(f"  written to {savePath}")
                else:
                    print(f"  no such command: {command}. /help lists them.")
                continue

            try:
                lastResult = Cycle.RDFChatTurn(
                    rdfGraph, message, history=history, llm=llm, schema=schema, chains=chains,
                    vocabulary=vocabulary, meter=meter, confirm=confirm, maxTurns=maxTurns,
                    maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                    verbose=verbose,
                )
            except OSError as exc:
                # The remote model is unreachable: every following turn would fail the same way
                print(f"\n{exc}\n")
                break

            history, schema = lastResult["history"], lastResult["schema"]
            chains = lastResult["chains"]
            saveNote = ""
            if lastResult["applied"]:
                edits, unsaved = edits + 1, True
                if autoSave and savePath is not None:
                    try:
                        rdfGraph.serialize(destination=str(savePath), format="turtle")
                        unsaved = False
                        saveNote = f"     saved to {Path(savePath).name}"
                    except OSError as exc:
                        # A file open elsewhere, or a read-only folder. The edit is still in
                        # the graph, so the session goes on and /save can be tried again.
                        saveNote = f"     could not write {Path(savePath).name}: {exc}"

            print(f"\nbot> {lastResult['answer']}")
            if saveNote:
                print(saveNote)
            if not silent and lastResult["sparql"]:
                # The answer reads the same whether the query was right or backwards, so the
                # query is the part worth putting in front of the user by default
                label = "update" if lastResult["intent"] == "edit" else "query"
                print(f"\n     the {label} it ran:")
                for line in lastResult["sparql"].splitlines():
                    print(f"       {line}")
            if verbose and lastResult["source"]:
                print(f"     grounded in {len(lastResult['source'])} node(s): "
                      f"{', '.join(lastResult['source'][:5])}")
            if not silent:
                running = meter.Total()
                print(f"\n     this turn: {lastResult['usage']['calls']} call(s), "
                      f"{CostMeter.Describe(lastResult['usage'])}")
                print(f"     so far:    {running['calls']} call(s), "
                      f"{CostMeter.Describe(running)}")
            print()

        if unsaved:
            print(f"{edits} edit(s) are in memory only. /save writes them" +
                  (f" to {savePath}." if savePath else ", once a savePath is given."))
        elif edits:
            print(f"{edits} edit(s) written to {savePath}.")

        total = meter.Total()
        if not silent:
            print(f"\nConversation: {len(history)} turn(s), {total['calls']} call(s), "
                  f"{CostMeter.Describe(total)}")

        return {
            "history": history,
            "graph": rdfGraph,
            "schema": schema,
            "chains": chains,
            "edits": edits,
            "saved": not unsaved,
            "usage": total,
        }

    @staticmethod
    def SQLiteQueryByPrompt(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        prompt: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        sourceColumn: str = "sosa:madeBySensor",
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Answer a natural-language question about an observation table, through a hosted LLM.

        Cycle.RDFQueryByPrompt with the graph swapped for a SQLite database written in the
        shape of Observation.Template - the same five steps, three of them model calls:
        1. Observation.SQLiteIndex and 2. Observation.SQLiteSchemaSummary describe the table
           (no model);
        3. Tool.SQLiteWriteSQL turns the question into a query;
        4. SQL.Validate checks it, Tool.SQLiteRepairSQL rewrites it when it fails;
        5. Observation.SQLiteFetch runs it read-only (no model), then Tool.SQLiteAnswer words
           the result.

        Two things are easier here than on the graph, and one is harder. Easier: SQLite can
        compile a query without running it, so a hallucinated column is caught by name rather
        than showing up as an empty result; and the connection is opened read-only, so the
        safety pass has the engine behind it rather than a regex alone. Harder: a table has
        no labels and no types, so what a sensor identifier means is something only the
        caller knows - which is what `notes` is for.

        The facts come from the data, not from the model: the answer is written only from the
        rows the query returned.

        Args:
            sqlitePath: Path to the SQLite database to answer from.
            tableName: The table holding the observations.
            prompt: The question in natural language.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of Observation.SQLiteSchemaSummary, reused across questions
                when supplied. Computed here when not, and it describes the table as it is
                now: pass a fresh one after new observations land.
            notes: Domain context for the schema block - what a sensor identifier is built
                from, say. Ignored when `schema` is supplied, since that already carries it.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected query may be sent back to be fixed.
            emptyRetries: How many times a valid but empty query is rewritten.
            rowLimit: Maximum rows a generated query may return.
            sourceColumn: The identifying column collected into 'source'.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'answer': str,        # the natural-language answer
                'sql': str,           # the query that produced the rows
                'rows': list[dict],   # the retrieved rows
                'source': list[str],  # the sensors the answer is grounded in
                'attempts': int,      # validation passes needed
                'usage': dict,        # tokens and cost for this question
            }

        Raises:
            ImportError: If `langchain-openai` is not installed.
            ValueError:  If inputs are missing, the table is not in the database, or no
                runnable query could be obtained.
            OSError:     If the model provider could not be reached.
        """
        if not sqlitePath or not isinstance(sqlitePath, str) or not sqlitePath.strip():
            raise ValueError("sqlitePath must be a non-empty string path.")
        if schema is None and (not tableName or not isinstance(tableName, str) or not tableName.strip()):
            raise ValueError("tableName must be a non-empty string.")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")

        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = Observation.SQLiteSchemaSummary(sqlitePath, tableName, notes=notes)
        meter = meter if meter is not None else CostMeter()

        grounding = schema["text"]
        columns = schema.get("columns")

        # Where this question's calls start, so its cost can be split out of the run total
        first = len(meter.calls)

        sql = Tool.SQLiteWriteSQL(llm, grounding, prompt, meter, rowLimit)
        if verbose:
            print(f"\n[agent 3] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 3] proposed query:\n{sql}")

        # Agent 4 rejects, the repair chain rewrites, until it holds or the budget runs out
        attempts = 0
        for attempts in range(1, maxRepairs + 2):
            checked, error = SQL.Validate(sql, sqlitePath, rowLimit, columns)
            if checked is not None:
                sql = checked
                break
            if verbose:
                print(f"[agent 4] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(f"No runnable query after {attempts} attempt(s). Last error: {error}")
            previous = sql
            sql = Tool.SQLiteRepairSQL(llm, grounding, prompt, sql, error, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 4] repaired query:\n{sql}")
            if sql.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempts} attempt(s): the model returned the query "
                    f"it was just asked to fix, so further retries would be identical. Raise "
                    f"`temperature` on the LLM so retries can differ, or rephrase the question. "
                    f"Last error: {error}")

        if verbose:
            print("[agent 4] accepted")

        rows = Observation.SQLiteFetch(sqlitePath, sql)
        if verbose:
            print(f"[agent 5] {len(rows)} row(s), no model call")

        # An empty result is the one failure the validator cannot see: real columns, clean
        # compile, a literal that is not in the table. Give it back to the repair chain, but
        # keep the rewrite only if it actually finds data - otherwise the original query
        # stands and the empty answer is real. 'Empty' here is _NoData rather than `not rows`,
        # because an aggregate that matched nothing still returns a row: see its docstring.
        for retry in range(emptyRetries):
            if not _NoData(rows):
                break
            if verbose:
                print(f"[agent 4] empty result, asking for a rewrite ({retry + 1}/{emptyRetries})")

            candidate = Tool.SQLiteRepairSQL(
                llm, grounding, prompt, sql, Tool.SQLITE_EMPTY_RESULT_REASON, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")

            checked, error = SQL.Validate(candidate, sqlitePath, rowLimit, columns)
            if checked is None:
                if verbose:
                    print(f"[agent 4] rewrite rejected: {error} - keeping the empty result")
                break

            try:
                candidateRows = Observation.SQLiteFetch(sqlitePath, checked)
            except sqlite3.DatabaseError as exc:
                # EXPLAIN compiled it but running it did not: keep what we already have
                if verbose:
                    print(f"[agent 5] rewrite failed to run: {exc} - keeping the empty result")
                break

            if verbose:
                print(f"[agent 4] rewritten query:\n{checked}")
                print(f"[agent 5] {len(candidateRows)} row(s) after rewrite")
            if not _NoData(candidateRows):
                sql, rows = checked, candidateRows

        answer = Tool.SQLiteAnswer(llm, prompt, rows, meter, rowLimit)
        if verbose:
            print(f"[answer]  {CostMeter.Describe(meter.calls[-1])}")

        return {
            "answer": answer,
            "sql": sql,
            "rows": rows,
            "source": Observation.SQLiteSourceRows(rows, sourceColumn),
            "attempts": attempts,
            "usage": meter.Total(first),
        }

    @staticmethod
    def SQLiteEditByPrompt(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        prompt: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        meter: Optional[CostMeter] = None,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        inPlace: bool = False,
        savePath: Optional[str] = None,
        diffLimit: int = 20000,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Change a table of observations by describing the change.

        Cycle.RDFEditByPrompt's counterpart on the table side, and Cycle.SQLiteQueryByPrompt
        with the safety catch turned the other way: there the model writes a SELECT and may
        not write, here it writes an INSERT, an UPDATE or a DELETE and nothing else.

        Two agents: Tool.SQLiteWriteUpdate turns the instruction into SQL, SQL.ValidateUpdate
        checks it, and Tool.SQLiteRepairUpdate rewrites it when it fails.
        Observation.SQLiteApplyUpdate then REHEARSES it - runs it inside a transaction, reads
        the diff, and rolls back - so nothing reaches the file until a statement has run and
        its effect has been seen.

        Where the result goes is the caller's to choose, and the default choice is the safe one:

        - neither `inPlace` nor `savePath`: a dry run. The diff comes back, the database is
          untouched, and 'committed' is False. This is the mode to read before trusting.
        - `savePath`: the database is copied there and the edit committed to the copy, so the
          original is left as it was - the file-level equivalent of the copy that
          Tool.RDFApplyUpdate hands back.
        - `inPlace=True`: committed to `sqlitePath` itself.

        Four things bound what the model may do: the statement must open with INSERT, UPDATE
        or DELETE; an UPDATE or a DELETE must carry a WHERE clause, so it cannot empty the
        table; REPLACE is refused, so an addition cannot silently delete; and it may write to
        no table but the one named. SQL.ValidateUpdate explains why each of those is there.

        Args:
            sqlitePath: Path to the SQLite database to edit.
            tableName: The table holding the observations.
            prompt: The change, in natural language.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of Observation.SQLiteSchemaSummary, recomputed here when not
                supplied. It describes the table BEFORE the edit: pass a fresh one for the
                next edit, or a query written against it will not know what was added.
            notes: Domain context for the schema block. Ignored when `schema` is supplied.
            meter: A CostMeter to tally token usage and cost into.
            maxRepairs: How many times a rejected statement may be sent back to be fixed.
            emptyRetries: How many times a statement that changes nothing is rewritten.
            inPlace: Commit to `sqlitePath`. Mutually exclusive with `savePath`.
            savePath: Commit to a copy of the database written here, leaving the original as
                it was. Mutually exclusive with `inPlace`.
            diffLimit: Passed through to Observation.SQLiteApplyUpdate: above this many rows
                the table is not diffed and only the change count comes back.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'database': str,      # the file holding the result, '' after a dry run
                'sql': str,           # the statement that produced it
                'changes': int,       # rows the statement moved
                'added': list[dict],  # rows added
                'removed': list[dict],# rows removed
                'attempts': int,      # validation passes needed
                'committed': bool,    # whether anything was written to disk
                'usage': dict,        # tokens and cost for this edit
            }

        Raises:
            ImportError: If `langchain-openai` is not installed.
            ValueError:  If inputs are missing or contradictory, the table is not in the
                database, or no runnable statement could be obtained.
            OSError:     If the model provider could not be reached.
        """
        if not sqlitePath or not isinstance(sqlitePath, str) or not sqlitePath.strip():
            raise ValueError("sqlitePath must be a non-empty string path.")
        if not tableName or not isinstance(tableName, str) or not tableName.strip():
            raise ValueError("tableName must be a non-empty string.")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if inPlace and savePath:
            raise ValueError(
                "Pass inPlace=True to commit to sqlitePath, or savePath to commit to a copy "
                "of it, not both: they name two different places for the same edit to land.")

        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = Observation.SQLiteSchemaSummary(sqlitePath, tableName, notes=notes)
        meter = meter if meter is not None else CostMeter()

        grounding = schema["text"]
        columns = schema.get("columns")
        first = len(meter.calls)

        def run(candidate: str, attempt: int):
            """Validate, then rehearse. One rejection reason whichever step said no."""
            checked, error = SQL.ValidateUpdate(candidate, tableName, sqlitePath, columns)
            if checked is None:
                return None, 0, [], [], error
            changes, added, removed, error = Observation.SQLiteApplyUpdate(
                sqlitePath, tableName, checked, commit=False, diffLimit=diffLimit)
            if error:
                return None, 0, [], [], error
            if verbose:
                print(f"[agent 2] accepted (pass {attempt})")
                print(f"[rehearse] {changes} row(s) changed: "
                      f"+{len(added)} / -{len(removed)}, rolled back")
            return checked, changes, added, removed, ""

        sql = Tool.SQLiteWriteUpdate(llm, grounding, prompt, meter)
        if verbose:
            print(f"\n[agent 1] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 1] proposed statement:\n{sql}")

        # Agent 2 rejects, the repair chain rewrites, until it runs or the budget runs out
        accepted, changes, added, removed, attempts = None, 0, [], [], 0
        for attempts in range(1, maxRepairs + 2):
            accepted, changes, added, removed, error = run(sql, attempts)
            if accepted is not None:
                sql = accepted
                break
            if verbose:
                print(f"[agent 2] rejected ({attempts}/{maxRepairs + 1}): {error}")
            if attempts > maxRepairs:
                raise ValueError(f"No runnable statement after {attempts} attempt(s). "
                                 f"Last error: {error}")
            previous = sql
            sql = Tool.SQLiteRepairUpdate(llm, grounding, prompt, sql, error, meter)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 2] repaired statement:\n{sql}")
            if sql.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempts} attempt(s): the model returned the "
                    f"statement it was just asked to fix, so further retries would be "
                    f"identical. Raise `temperature` on the LLM so retries can differ, or "
                    f"phrase the request as something expressible in one statement. "
                    f"Last error: {error}")

        # A statement that changes nothing is this cycle's empty SELECT: real columns, clean
        # compile, a WHERE clause the data does not satisfy. Keep a rewrite only when it
        # actually moves a row - otherwise the original stands and the caller is told plainly
        # that the table is unchanged.
        for retry in range(emptyRetries):
            if changes:
                break
            if verbose:
                print(f"[agent 2] nothing changed, asking for a rewrite ({retry + 1}/{emptyRetries})")

            candidate = Tool.SQLiteRepairUpdate(
                llm, grounding, prompt, sql, Tool.SQLITE_NO_CHANGE_REASON, meter)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")

            rewritten, rewrittenChanges, rewrittenAdded, rewrittenRemoved, error = run(
                candidate, attempts)
            if rewritten is None:
                if verbose:
                    print(f"[agent 2] rewrite rejected: {error} - keeping the unchanged table")
                break
            if rewrittenChanges:
                sql, changes = rewritten, rewrittenChanges
                added, removed = rewrittenAdded, rewrittenRemoved

        # Only now, with a statement that ran and a change that can be shown, is anything on
        # disk allowed to move. The rehearsal rolled back, so this runs against the same state
        # it did and lands the same diff.
        database, committed = "", False
        if changes and (inPlace or savePath):
            target = Observation.SQLiteCopy(sqlitePath, savePath) if savePath else sqlitePath
            _, _, _, error = Observation.SQLiteApplyUpdate(
                target, tableName, sql, commit=True, diffLimit=0)
            if error:
                raise ValueError(f"The statement rehearsed cleanly but failed to commit: {error}")
            database, committed = target, True
            if verbose:
                print(f"[commit]  {changes} row(s) written to {target}")
        elif verbose:
            print("[commit]  nothing written: "
                  + ("the statement changed no rows" if not changes
                     else "dry run, pass inPlace=True or savePath to keep it"))

        return {
            "database": database,
            "sql": sql,
            "changes": changes,
            "added": added,
            "removed": removed,
            "attempts": attempts,
            "committed": committed,
            "usage": meter.Total(first),
        }

    @staticmethod
    def SQLiteChatTurn(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        message: Optional[str] = None,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        meter: Optional[CostMeter] = None,
        confirm: Optional[Callable[[Dict[str, Any]], bool]] = None,
        maxTurns: int = 8,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        sourceColumn: str = "sosa:madeBySensor",
        diffLimit: int = 20000,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Take one turn of a conversation about a table of observations.

        Cycle.RDFChatTurn's counterpart on the table side, and the same orchestration:
        Tool.ChatRoute reads the conversation and turns the message into a self-contained
        request with an intent, and that request goes to Cycle.SQLiteQueryByPrompt to be
        answered or Cycle.SQLiteEditByPrompt to be applied. Neither of those knows a
        conversation is happening - the memory is spent entirely on the rewrite, so an answer
        is still written from retrieved rows and nothing else.

        Nothing is read from or written to a terminal here, and the database does not move on
        its own: an edit is rehearsed inside a transaction that is rolled back, and `confirm`
        decides whether it is then committed. Cycle.SQLiteChat supplies a `confirm` that
        prints the diff and asks; another caller can pass `lambda proposal: True` to commit
        every edit, or leave it None to see what an edit would do without doing it. The file
        the caller names is the file that moves, so point this at a copy when the original
        matters - which is what Cycle.SQLiteChat's `savePath` does.

        The turn is stateless. `history` is not modified: the returned dict carries a new list
        with this turn appended, and the caller passes it back for the next one.

        Args:
            sqlitePath: The database to answer from and, when an edit is confirmed, to edit.
            tableName: The table holding the observations.
            message: What the user just typed, ellipsis and pronouns and all.
            history: Turns from the previous calls, as returned in 'history'.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of Observation.SQLiteSchemaSummary. Computed here when not
                supplied, and recomputed after a committed edit - it describes the table as
                it was, so the next question would otherwise be grounded in a VALUES list
                that no longer matches the data.
            notes: Domain context for the schema block. Ignored when `schema` is supplied.
            meter: A CostMeter to tally token usage and cost into.
            confirm: Called with the rehearsed edit before anything is committed, and the edit
                is committed only if it returns True. None never commits.
            maxTurns: How many past turns the router is shown.
            maxRepairs: How many times a rejected query or statement may be sent back.
            emptyRetries: How many times an empty result or a no-op statement is rewritten.
            rowLimit: Maximum rows a generated SELECT may return.
            sourceColumn: The identifying column collected into 'source'.
            diffLimit: Passed through to the edit cycle.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'answer': str,        # what to show the user
                'intent': str,        # 'question', 'edit' or 'talk'
                'request': str,       # the message, restated to stand alone
                'sql': str,           # the query or statement, '' for a 'talk' turn
                'rows': list[dict],   # rows retrieved, for a question
                'source': list[str],  # the sensors the answer is grounded in
                'changes': int,       # rows an edit proposed moving
                'added': list[dict],  # rows an edit proposed adding
                'removed': list[dict],# rows an edit proposed removing
                'applied': bool,      # whether the edit reached the database
                'error': str | None,  # why a question or edit could not be served
                'history': list,      # `history` with this turn appended
                'schema': dict,       # the schema to pass to the next turn
                'usage': dict,        # tokens and cost for this turn
            }

        Raises:
            ImportError: If `langchain-openai` is not installed.
            ValueError:  If inputs are missing, or the table is not in the database.
            TypeError:   If `history` is not a list, or `confirm` is not callable.
            OSError:     If the model provider could not be reached. A conversation cannot
                continue through this, so it is left to reach the caller.
        """
        if not sqlitePath or not isinstance(sqlitePath, str) or not sqlitePath.strip():
            raise ValueError("sqlitePath must be a non-empty string path.")
        if not tableName or not isinstance(tableName, str) or not tableName.strip():
            raise ValueError("tableName must be a non-empty string.")
        if not message or not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")
        if history is not None and not isinstance(history, list):
            raise TypeError("history must be a list.")
        if confirm is not None and not callable(confirm):
            raise TypeError("confirm must be callable.")

        history = list(history or [])
        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = Observation.SQLiteSchemaSummary(sqlitePath, tableName, notes=notes)
        meter = meter if meter is not None else CostMeter()

        # Where this turn's calls start, so its cost can be split out of the run total
        first = len(meter.calls)

        routed = Tool.ChatRoute(
            llm, Tool.ChatTranscript(history, maxTurns), message, meter,
            Tool.CHAT_TABLE_ROUTER_PROMPT)
        intent, request = routed["intent"], routed["request"]
        if verbose:
            print(f"\n[router]  {CostMeter.Describe(meter.calls[-1])}")
            print(f"[router]  {intent}: {request}")

        answer, sql, error = "", "", None
        rows: List[Dict[str, Any]] = []
        source: List[str] = []
        added: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []
        changes, applied = 0, False

        if intent == "talk":
            answer = Tool.ChatReply(
                llm, Tool.ChatTranscript(history, maxTurns), message, meter,
                Tool.CHAT_TABLE_TALK_PROMPT)
            if verbose:
                print(f"[talk]    {CostMeter.Describe(meter.calls[-1])}")

        elif intent == "edit":
            # A rejected statement or an unfixable one ends this turn, not the conversation:
            # the user is told and can rephrase. Only OSError, the model being unreachable,
            # gets to end the session, and that is left to propagate.
            try:
                result = Cycle.SQLiteEditByPrompt(
                    sqlitePath, tableName, request, llm=llm, schema=schema, meter=meter,
                    maxRepairs=maxRepairs, emptyRetries=emptyRetries, diffLimit=diffLimit,
                    verbose=verbose,
                )
            except ValueError as exc:
                error = str(exc)
                answer = f"I could not make that change: {exc}"
            else:
                sql, changes = result["sql"], result["changes"]
                added, removed = result["added"], result["removed"]
                if not changes:
                    answer = ("That change would leave the table exactly as it is: no row "
                              "matches what you described.")
                elif confirm is not None and confirm({
                    "request": request, "sql": sql, "changes": changes,
                    "added": added, "removed": removed,
                }):
                    # The rehearsal rolled back, so the same statement runs again against the
                    # same state and lands the same diff. Re-running the SQL rather than
                    # re-running the cycle costs nothing: the model has already done its work.
                    _, _, _, failure = Observation.SQLiteApplyUpdate(
                        sqlitePath, tableName, sql, commit=True, diffLimit=0)
                    if failure:
                        error = failure
                        answer = f"The change rehearsed cleanly but would not commit: {failure}"
                    else:
                        applied = True
                        # The table has moved, so what describes it is now the old
                        # description. The index is read alongside it for the row count,
                        # which the schema summary does not carry on its own.
                        index = Observation.SQLiteIndex(sqlitePath, tableName)
                        schema = Observation.SQLiteSchemaSummary(
                            sqlitePath, tableName, index, notes=notes)
                        answer = (f"Done: {len(added)} row(s) added, {len(removed)} removed. "
                                  f"The table now holds {index['rows']} rows.")
                else:
                    answer = ("Left the table as it was. The change is described above if you "
                              "want to ask for it differently.")

        else:
            try:
                result = Cycle.SQLiteQueryByPrompt(
                    sqlitePath, tableName, request, llm=llm, schema=schema, meter=meter,
                    maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                    sourceColumn=sourceColumn, verbose=verbose,
                )
            except ValueError as exc:
                error = str(exc)
                answer = f"I could not answer that: {exc}"
            else:
                answer, sql = result["answer"], result["sql"]
                rows, source = result["rows"], result["source"]

        turn = {"message": message.strip(), "intent": intent, "request": request,
                "answer": answer, "sql": sql, "applied": applied}

        return {
            "answer": answer,
            "intent": intent,
            "request": request,
            "sql": sql,
            "rows": rows,
            "source": source,
            "changes": changes,
            "added": added,
            "removed": removed,
            "applied": applied,
            "error": error,
            "history": history + [turn],
            "schema": schema,
            "usage": meter.Total(first),
        }

    @staticmethod
    def SQLiteChat(
        sqlitePath: Optional[str] = None,
        tableName: Optional[str] = None,
        *,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        meter: Optional[CostMeter] = None,
        savePath: Optional[Union[str, Path]] = None,
        inPlace: bool = False,
        maxTurns: int = 8,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        sourceColumn: str = "sosa:madeBySensor",
        diffLimit: int = 20000,
        silent: bool = False,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Hold a conversation about a table of observations at the terminal.

        A loop around Cycle.SQLiteChatTurn, and Cycle.RDFChat's counterpart on the table side:
        it prints the answers, asks before an edit lands, and keeps the history and the schema
        threaded from one turn to the next. Everything it knows about the building it gets
        from that one call.

        Every turn shows the query it was answered from and what it cost, because the reading
        that catches a wrong answer here is the query, not the sentence: a filter on a literal
        that is not in the table is valid, cheap and confidently empty.

        Where a confirmed edit lands is decided once, before the first turn, and said out loud:

        - `savePath`: the database is copied there and the whole conversation talks to the
          copy. The original is never opened for writing. This is the mode to use, and the
          direct equivalent of Cycle.RDFChat editing a graph in memory rather than the file it
          was read from.
        - `inPlace=True`: the conversation edits `sqlitePath` itself. There is no undo.
        - neither: questions are answered and edits are rehearsed and shown, but nothing can
          be kept. The session says so when an edit is refused for that reason, rather than
          asking a question whose answer cannot be honoured.

        Escape leaves at the prompt, as do /exit, Ctrl-C and end of input. At the confirmation
        of an edit it means no - refusing a change is not a reason to end the conversation.

        The commands, typed at the prompt:

            /help      what can be typed here
            /sql       the query or statement behind the last answer
            /rows      the rows the last answer was written from
            /history   the conversation as the router sees it
            /schema    the grounding block the model is given
            /cost      what the conversation has cost so far
            /silent    stop showing the query and the cost of each turn, or show them again
            /verbose   show each agent's step and cost, or stop showing them
            /exit      leave, /quit does the same

        There is no /save: a committed edit is already on disk, because a database is the file
        rather than something serialised into one. That is what `savePath` is for.

        Args:
            sqlitePath: The database to talk about.
            tableName: The table holding the observations.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of Observation.SQLiteSchemaSummary. Computed here when not
                supplied, and kept current across edits.
            notes: Domain context for the schema block - what a sensor identifier is built
                from, say. Ignored when `schema` is supplied.
            meter: A CostMeter to tally token usage and cost into.
            savePath: Where the edited database is written. Copied from `sqlitePath` before
                the first turn, so the original is left alone. Mutually exclusive with
                `inPlace`.
            inPlace: Edit `sqlitePath` itself. Mutually exclusive with `savePath`.
            maxTurns: How many past turns the router is shown.
            maxRepairs: How many times a rejected query or statement may be sent back.
            emptyRetries: How many times an empty result or a no-op statement is rewritten.
            rowLimit: Maximum rows a generated SELECT may return.
            sourceColumn: The identifying column reported as an answer's source.
            diffLimit: Passed through to the edit cycle.
            silent: Print the answers and nothing else - no query behind each turn, no running
                cost, no closing total. /silent toggles it.
            verbose: Start with the per-agent narration on. /verbose toggles it.

        Returns:
            dict: {
                'history': list,    # every turn taken
                'database': str,    # the file the conversation talked to
                'schema': dict,     # the schema as it stands at the end
                'edits': int,       # how many edits were committed
                'editable': bool,   # whether an edit could be kept at all
                'usage': dict,      # tokens and cost for the whole conversation
            }

        Raises:
            ImportError: If `langchain-openai` is not installed.
            ValueError:  If inputs are missing or contradictory, or the table is not in the
                database.
        """
        if not sqlitePath or not isinstance(sqlitePath, str) or not sqlitePath.strip():
            raise ValueError("sqlitePath must be a non-empty string path.")
        if not tableName or not isinstance(tableName, str) or not tableName.strip():
            raise ValueError("tableName must be a non-empty string.")
        if inPlace and savePath:
            raise ValueError(
                "Pass inPlace=True to edit sqlitePath, or savePath to edit a copy of it, not "
                "both: they name two different databases for the conversation to talk to.")

        # Decided once, before anything is asked, so a session cannot reach the confirmation
        # of an edit only to discover it has nowhere to put it
        if savePath:
            database = Observation.SQLiteCopy(sqlitePath, str(savePath))
            editable = True
        else:
            database = sqlitePath
            editable = bool(inPlace)

        llm = llm if llm is not None else LLM.Constructor()
        index = Observation.SQLiteIndex(database, tableName)
        if schema is None:
            schema = Observation.SQLiteSchemaSummary(database, tableName, index, notes=notes)
        meter = meter if meter is not None else CostMeter()

        history: List[Dict[str, Any]] = []
        lastResult: Optional[Dict[str, Any]] = None
        edits = 0

        def confirm(proposal: Dict[str, Any]) -> bool:
            """Show the diff and ask. A model-written statement is not committed unseen."""
            print("\n  the change it proposes:")
            for row in proposal["removed"]:
                print(f"    - {row}")
            for row in proposal["added"]:
                print(f"    + {row}")
            if not proposal["added"] and not proposal["removed"]:
                print(f"    {proposal['changes']} row(s), too many to list")
            try:
                reply = _ReadLine("  apply? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                # Ctrl-C at the confirmation refuses the edit; it does not end the session
                print()
                return False
            # Escape here is the same answer as anything that is not yes: leave the table alone
            return reply is not None and reply.strip().lower() in ("y", "yes")

        def refuse(proposal: Dict[str, Any]) -> bool:
            """Show what an edit would do, then decline it: there is nowhere to keep it."""
            print("\n  the change it proposes:")
            for row in proposal["removed"]:
                print(f"    - {row}")
            for row in proposal["added"]:
                print(f"    + {row}")
            print("  not applied: pass savePath to edit a copy, or inPlace=True to edit "
                  "this database.")
            return False

        print(f"\nChatting about {index['rows']} observations in '{tableName}', "
              f"via {llm.model_name}.")
        if savePath:
            print(f"Edits go to the copy at {database}; the original is left as it is.")
        elif inPlace:
            print(f"Edits are committed to {database} itself. There is no undo.")
        else:
            print("Read-only: edits are shown but cannot be kept. Pass savePath to keep them.")
        print("Ask a question, or describe a correction. /help for commands, "
              "Esc or /exit to leave.\n")

        while True:
            try:
                line = _ReadLine("you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line is None:            # Escape
                break
            message = line.strip()
            if not message:
                continue

            if message.startswith("/"):
                command = message.split()[0].lower()
                if command in ("/exit", "/quit"):
                    break
                elif command == "/help":
                    print("  /sql  /rows  /history  /schema  /cost  /silent  /verbose  /exit")
                    print("  Esc leaves too, and answers no to an edit.")
                elif command == "/sql":
                    print(f"\n{lastResult['sql'] or '(no query behind that answer)'}\n"
                          if lastResult else "  nothing asked yet")
                elif command == "/rows":
                    if not lastResult or not lastResult["rows"]:
                        print("  no rows behind that answer")
                    else:
                        for row in lastResult["rows"][:20]:
                            print(f"    {row}")
                        if len(lastResult["rows"]) > 20:
                            print(f"    ... and {len(lastResult['rows']) - 20} more")
                elif command == "/history":
                    print(f"\n{Tool.ChatTranscript(history, maxTurns)}\n")
                elif command == "/schema":
                    print(f"\n{schema['text']}\n")
                elif command == "/cost":
                    total = meter.Total()
                    print(f"  {total['calls']} call(s), {CostMeter.Describe(total)}")
                elif command == "/silent":
                    silent = not silent
                    print(f"  silent {'on' if silent else 'off'}")
                elif command == "/verbose":
                    verbose = not verbose
                    print(f"  verbose {'on' if verbose else 'off'}")
                else:
                    print(f"  no such command: {command}. /help lists them.")
                continue

            try:
                lastResult = Cycle.SQLiteChatTurn(
                    database, tableName, message, history=history, llm=llm, schema=schema,
                    notes=notes, meter=meter, confirm=confirm if editable else refuse,
                    maxTurns=maxTurns, maxRepairs=maxRepairs, emptyRetries=emptyRetries,
                    rowLimit=rowLimit, sourceColumn=sourceColumn, diffLimit=diffLimit,
                    verbose=verbose,
                )
            except OSError as exc:
                # The remote model is unreachable: every following turn would fail the same way
                print(f"\n{exc}\n")
                break

            history, schema = lastResult["history"], lastResult["schema"]
            if lastResult["applied"]:
                edits += 1

            print(f"\nbot> {lastResult['answer']}")
            if not silent and lastResult["sql"]:
                # The answer reads the same whether the query was right or filtered on a
                # literal that is not there, so the query is the part worth showing by default
                label = "statement" if lastResult["intent"] == "edit" else "query"
                print(f"\n     the {label} it ran:")
                for line in lastResult["sql"].splitlines():
                    print(f"       {line}")
            if verbose and lastResult["source"]:
                print(f"     grounded in {len(lastResult['source'])} sensor(s): "
                      f"{', '.join(lastResult['source'][:5])}")
            if not silent:
                running = meter.Total()
                print(f"\n     this turn: {lastResult['usage']['calls']} call(s), "
                      f"{CostMeter.Describe(lastResult['usage'])}")
                print(f"     so far:    {running['calls']} call(s), "
                      f"{CostMeter.Describe(running)}")
            print()

        if edits:
            print(f"{edits} edit(s) committed to {database}.")

        total = meter.Total()
        if not silent:
            print(f"\nConversation: {len(history)} turn(s), {total['calls']} call(s), "
                  f"{CostMeter.Describe(total)}")

        return {
            "history": history,
            "database": database,
            "schema": schema,
            "edits": edits,
            "editable": editable,
            "usage": total,
        }

    @staticmethod
    def TwinQueryByPrompt(
        rdfGraph=None,
        prompt: Optional[str] = None,
        *,
        basePath: Optional[Union[str, Path]] = None,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        chains: Optional[List[Dict[str, Any]]] = None,
        meter: Optional[CostMeter] = None,
        tableName: str = "observations",
        notes: Optional[str] = None,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        maxDatabases: int = 25,
        locatorRepairs: int = 1,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Answer a question about a twin: a graph, and the databases the graph points at.

        The orchestrator over Cycle.RDFQueryByPrompt and Cycle.SQLiteQueryByPrompt. Those two
        each own one half of a twin and cannot see the other: the graph knows a building has
        four spaces of 505 m2 and nothing about its meter, the database knows 29,285 kWh and
        nothing about whose kilowatt hours they are. This joins them, using the one thing that
        spans both - a document node whose property set records where a database is.

        Six steps, four of which call a model:

        1. Tool.TwinRoute reads the question and decides what it needs: the graph alone, the
           readings alone, or both. A 'graph' question is handed to Cycle.RDFQueryByPrompt and
           this cycle does nothing else.
        2. Tool.TwinWriteLocator writes SPARQL that returns the databases to open, with the
           node that owns each. SPARQL.Validate checks it and Tool.TwinRepairLocator rewrites
           it when it fails.
        3. Tool.TwinTargets resolves those rows to files that are actually on disk (no model).
        4. Tool.SQLiteWriteSQL writes ONE query for the whole selected set, grounded on a
           representative database and told it will be fanned out.
        5. SQL.Validate compiles that query against EVERY selected database before any of them
           is read, then each is read and its rows tagged with the building they came from
           (no model).
        6. Tool.TwinAnswer words the result from those rows, and - for a 'both' question -
           from Tool.TwinEstateBlock beside them, so 'per square metre' has both halves.

        The cost is flat in the number of databases: four model calls whether the question
        touches one building or twenty.

        Args:
            rdfGraph: An rdflib.Graph describing the estate, including the document nodes
                that record where its databases are.
            prompt: The question in natural language.
            basePath: The directory the graph's file paths are relative to. Defaults to the
                working directory, which is right only when it happens to be where the graph
                was written - pass it explicitly.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary, reused across questions when supplied.
            chains: The output of RDF.Chains, used by the 'graph' path.
            meter: A CostMeter to tally token usage and cost into.
            tableName: The table to read in a database whose graph entry does not name one.
            notes: Domain context appended to the table description, as for
                Cycle.SQLiteQueryByPrompt.
            maxRepairs: How many times a rejected locator or query may be sent back.
            emptyRetries: How many times an empty locator or an empty result is rewritten.
            rowLimit: Maximum rows a generated query may return, per database.
            maxDatabases: Refuse a fan-out wider than this.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'answer': str,          # the natural-language answer
                'intent': str,          # 'graph', 'readings' or 'both'
                'sparql': str,          # the locator, or the graph query for a 'graph' turn
                'sql': str,             # the query run against each database
                'targets': list[dict],  # the databases opened, with their owner nodes
                'rows': list[dict],     # the merged readings, tagged with their building
                'estate': str,          # the graph figures shown beside them, '' when none
                'source': list[str],    # graph nodes the answer is grounded in
                'skipped': list[dict],  # databases the query would not compile against
                'attempts': int,        # validation passes the locator needed
                'usage': dict,          # tokens and cost for this question
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If inputs are missing, or no usable locator or query was obtained.
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
        first = len(meter.calls)

        empty: Dict[str, Any] = {
            "answer": "", "intent": "", "sparql": "", "sql": "", "targets": [], "rows": [],
            "estate": "", "source": [], "skipped": [], "attempts": 0, "usage": {},
            "fellBack": False, "reason": "",
        }

        intent = Tool.TwinRoute(llm, schema["text"], prompt, meter)
        if verbose:
            print(f"\n[router]  {CostMeter.Describe(meter.calls[-1])}")
            print(f"[router]  {intent}")

        # The schema says what the classes and predicates are; the property block says what
        # the properties HOLD, spelled exactly. Every agent that writes SPARQL here is given
        # both, and none of them can afford to be without it: a locator FILTERs on those
        # literals, and a question about the estate is written against those property names -
        # 'how big are they' asks for 'NetFloorArea', which is not a name anything can guess.
        located = f"{schema['text']}\n\n{Tool.TwinPropertyBlock(rdfGraph)}"
        grounded = {**schema, "text": located}

        # A question about the estate never opens a database. Handing it straight to the graph
        # cycle keeps one entry point for the caller without making the graph path pay for the
        # database path's machinery.
        if intent == "graph":
            result = Cycle.RDFQueryByPrompt(
                rdfGraph, prompt, llm=llm, schema=grounded, chains=chains, meter=meter,
                maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                verbose=verbose)
            return {**empty,
                    "answer": result["answer"], "intent": intent, "sparql": result["sparql"],
                    "rows": result["rows"], "source": result["source"],
                    "attempts": result["attempts"], "usage": meter.Total(first)}

        # --- Locate the databases ---------------------------------------------------------
        sparql = Tool.TwinWriteLocator(llm, located, prompt, meter, rowLimit)
        if verbose:
            print(f"\n[agent 1] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 1] proposed locator:\n{sparql}")

        def locate(candidate: str) -> Tuple[Optional[str], List[Dict[str, Any]], str]:
            """Validate, run, resolve to files. One reason back, whichever step said no."""
            checked, error = SPARQL.Validate(candidate, schema["terms"], rowLimit)
            if checked is None:
                return None, [], error
            try:
                rows = RDF.Query(rdfGraph, checked)
            except ValueError as exc:
                return None, [], f"The query parsed but would not run: {exc}"
            found, reason = Tool.TwinTargets(rows, basePath, maxDatabases)
            if not found:
                return None, [], reason
            return checked, found, ""

        # A locator that finds nothing is weak evidence about the query and strong evidence
        # about the question. A graph naming ten databases and matching none of them is
        # usually being asked for something the readings do not hold - a figure recorded on
        # the estate, most often - and repairing that is expensive and rarely works, because
        # each retry re-derives the same emptiness. So the budget here is small, and running
        # out of it hands the question to the graph rather than raising. 'fellBack' says so,
        # so a graph answer is never mistaken for a measured one.
        targets: List[Dict[str, Any]] = []
        attempts, stalled = 0, ""
        for attempts in range(1, locatorRepairs + 2):
            checked, targets, error = locate(sparql)
            if checked is not None:
                sparql = checked
                break
            if verbose:
                print(f"[agent 2] rejected ({attempts}/{locatorRepairs + 1}): {error}")
            if attempts > locatorRepairs:
                stalled = error
                break
            previous = sparql
            sparql = Tool.TwinRepairLocator(llm, located, prompt, sparql, error, meter)
            if verbose:
                print(f"[agent 2] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 2] repaired locator:\n{sparql}")
            if sparql.strip() == previous.strip():
                stalled = ("the model returned the query it was just asked to fix. "
                           f"Last error: {error}")
                break

        if stalled:
            if verbose:
                print(f"[agent 2] gave up locating: {stalled}")
                print("[agent 5] falling back to the graph - the question may not be about "
                      "the readings at all")
            result = Cycle.RDFQueryByPrompt(
                rdfGraph, prompt, llm=llm, schema=grounded, chains=chains, meter=meter,
                maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                verbose=verbose)
            return {**empty,
                    "answer": result["answer"], "intent": "graph", "sparql": result["sparql"],
                    "rows": result["rows"], "source": result["source"],
                    "attempts": attempts, "fellBack": True, "reason": stalled,
                    "usage": meter.Total(first)}

        if verbose:
            print(f"[agent 2] accepted: {len(targets)} database(s)")
            for target in targets:
                print(f"           {target['ownerLabel'] or target['owner']} -> {target['path']}")

        # --- Write one query for all of them ----------------------------------------------
        # Grounded on the first database: they share a schema, which is what makes one query
        # legitimate, and step 5 is what checks that assumption rather than assuming it.
        table = targets[0]["table"] or tableName
        tableSchema = Observation.SQLiteSchemaSummary(
            targets[0]["path"], table, notes=notes)
        grounding = f"{tableSchema['text']}\n\n{Tool.TwinSQLBlock(targets)}"

        sql = Tool.SQLiteWriteSQL(llm, grounding, prompt, meter, rowLimit)
        if verbose:
            print(f"\n[agent 3] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 3] proposed query:\n{sql}")

        def compile(candidate: str) -> Tuple[Optional[str], List[Dict[str, Any]], str]:
            """
            Compile the query against every selected database before reading any of them.

            One query over many files only works while the files agree. Checking them all
            costs no model call - SQLite compiles through EXPLAIN without executing - and it
            is the difference between a ranking that is missing a building and one that
            reports which building it could not read.
            """
            accepted, refused, firstError = None, [], ""
            for target in targets:
                checked, error = SQL.Validate(
                    candidate, target["path"], rowLimit, tableSchema["columns"])
                if checked is None:
                    refused.append({**target, "reason": error})
                    firstError = firstError or error
                else:
                    accepted = accepted or checked
            if accepted is None:
                return None, refused, firstError
            return accepted, refused, ""

        skipped: List[Dict[str, Any]] = []
        for attempt in range(1, maxRepairs + 2):
            checked, skipped, error = compile(sql)
            if checked is not None:
                sql = checked
                break
            if verbose:
                print(f"[agent 4] rejected ({attempt}/{maxRepairs + 1}): {error}")
            if attempt > maxRepairs:
                raise ValueError(f"No runnable query after {attempt} attempt(s). "
                                 f"Last error: {error}")
            previous = sql
            sql = Tool.SQLiteRepairSQL(llm, grounding, prompt, sql, error, meter)
            if verbose:
                print(f"[agent 4] {CostMeter.Describe(meter.calls[-1])}")
                print(f"[agent 4] repaired query:\n{sql}")
            if sql.strip() == previous.strip():
                raise ValueError(
                    f"Repair stalled after {attempt} attempt(s): the model returned the query "
                    f"it was just asked to fix. Last error: {error}")

        if verbose and skipped:
            for target in skipped:
                print(f"[agent 4] skipped {target['ownerLabel']}: {target['reason']}")

        # --- Read them --------------------------------------------------------------------
        readable = [t for t in targets if not any(s["path"] == t["path"] for s in skipped)]
        rows = Cycle._TwinFetch(readable, sql)
        if verbose:
            print(f"[agent 5] {len(rows)} row(s) from {len(readable)} database(s), no model call")

        # An empty fan-out is the query's version of an empty SELECT, and gets the same one
        # rewrite: kept only if it actually finds data across the same set of files.
        for retry in range(emptyRetries):
            if not _NoData(rows):
                break
            if verbose:
                print(f"[agent 4] empty result, asking for a rewrite ({retry + 1}/{emptyRetries})")
            candidate = Tool.SQLiteRepairSQL(
                llm, grounding, prompt, sql, Tool.SQLITE_EMPTY_RESULT_REASON, meter)
            checked, _refused, error = compile(candidate)
            if checked is None:
                if verbose:
                    print(f"[agent 4] rewrite rejected: {error} - keeping the empty result")
                break
            candidateRows = Cycle._TwinFetch(readable, checked)
            if not _NoData(candidateRows):
                sql, rows = checked, candidateRows

        estate = Tool.TwinEstateBlock(rdfGraph, targets) if intent == "both" else ""
        answer = Tool.TwinAnswer(llm, prompt, rows, estate, meter, rowLimit)
        if verbose:
            print(f"[answer]  {CostMeter.Describe(meter.calls[-1])}")

        return {
            "answer": answer,
            "intent": intent,
            "sparql": sparql,
            "sql": sql,
            "targets": targets,
            "rows": rows,
            "estate": estate,
            "source": [t["owner"] for t in targets if t["owner"]],
            "skipped": skipped,
            "attempts": attempts,
            "fellBack": False,
            "reason": "",
            "usage": meter.Total(first),
        }

    @staticmethod
    def _TwinFetch(targets: List[Dict[str, Any]], sql: str) -> List[Dict[str, Any]]:
        """
        Run one query against each database and tag every row with where it came from.

        The tagging is the whole point of the fan-out. No file knows its own building - that
        is in the graph, not in the readings - so a row that arrives without its owner cannot
        be ranked against a row from anywhere else, and 29,285 kWh means nothing until it is
        29,285 kWh of the Chemistry Laboratories.

        A database that will not answer is left out rather than aborting the others: it was
        already compiled successfully, so a failure here is the file moving or locking under
        us, and one unreadable building should not cost the answer the other nineteen.
        """
        rows: List[Dict[str, Any]] = []
        for target in targets:
            try:
                found = Observation.SQLiteFetch(target["path"], sql)
            except (ValueError, sqlite3.DatabaseError):
                continue
            for row in found:
                # The tags go first, so a rendered row reads 'building=... ' before its numbers
                rows.append({
                    "building": target["ownerLabel"] or target["owner"] or target["path"],
                    **({"measures": target["property"]} if target["property"] else {}),
                    **({"unit": target["unit"]} if target["unit"] else {}),
                    **row,
                })
        return rows

    @staticmethod
    def TwinChatTurn(
        rdfGraph=None,
        message: Optional[str] = None,
        *,
        basePath: Optional[Union[str, Path]] = None,
        baseIRI: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        chains: Optional[List[Dict[str, Any]]] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        confirm: Optional[Callable[[Dict[str, Any]], bool]] = None,
        notes: Optional[str] = None,
        tableName: str = "observations",
        maxTurns: int = 8,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        maxDatabases: int = 25,
        diffLimit: int = 20000,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Take one turn of a conversation about a twin, reading or writing either half of it.

        Cycle.RDFChatTurn's counterpart for a twin, and it routes twice rather than once,
        because a twin turn has one more thing to decide:

        1. Tool.ChatRoute resolves the ellipsis against the transcript and separates small
           talk from a question from a change. This is the only place memory is used.
        2. A question goes to Cycle.TwinQueryByPrompt, which decides for itself whether it
           needs the graph, the databases, or both.
        3. A change goes to Tool.TwinEditRoute, which decides which half it lands in:
           - 'graph'    - Cycle.RDFEditByPrompt writes a validated SPARQL update.
           - 'readings' - the databases are located through the graph, then
             Cycle.SQLiteEditByPrompt rehearses a statement against each.
           - 'derive'   - the databases are READ and the graph is WRITTEN: the readings are
             retrieved, Tool.TwinKPIPlan says what to record and from which column,
             Tool.TwinKPIObjects does the arithmetic in Python, and the resulting KPI nodes
             are added to the graph. This is the one operation neither half could do alone,
             and the reason a twin is worth having as one object.

        Nothing is written without `confirm`. Every path rehearses - a graph edit against a
        copy, a database edit inside a transaction that is rolled back, a derived KPI as a
        list of proposed values - and `confirm` decides whether it lands. None never applies.

        The turn is stateless. `history` is not modified: the returned dict carries a new list
        with this turn appended, and the caller passes it back for the next one.

        Args:
            rdfGraph: An rdflib.Graph describing the estate, including the documents that
                record where its databases are. Confirmed graph edits are applied to it.
            message: What the user just typed, ellipsis and pronouns and all.
            basePath: The directory the graph's file paths are relative to.
            baseIRI: The base the graph's identifiers were minted with, so a derived KPI set
                lands in the same namespace as the buildings it names.
            history: Turns from the previous calls, as returned in 'history'.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary. Computed here when not supplied, and
                recomputed after any confirmed graph edit - including a derived one, which
                adds classes the schema has never seen.
            chains: The output of RDF.Chains, handled the same way.
            vocabulary: The output of Tool.JSONLDVocabulary, used by the graph-edit path.
            meter: A CostMeter to tally token usage and cost into.
            confirm: Called with the rehearsed change before anything is written. None never
                writes.
            notes: Domain context for the SQL half.
            tableName: The table to read in a database whose graph entry does not name one.
            maxTurns: How many past turns the router is shown.
            maxRepairs: How many times a rejected query or statement may be sent back.
            emptyRetries: How many times an empty result is rewritten.
            rowLimit: Maximum rows a generated query may return, per database.
            maxDatabases: Refuse a fan-out wider than this.
            diffLimit: Passed through to the database-edit path.
            verbose: Print each step's output and cost as it goes.

        Returns:
            dict: {
                'answer': str,        # what to show the user
                'intent': str,        # 'question', 'talk', or 'edit:graph|readings|derive'
                'request': str,       # the message, restated to stand alone
                'sparql': str,        # the locator, graph query or graph update
                'sql': str,           # the query or statement run against the databases
                'rows': list[dict],   # readings retrieved, tagged with their building
                'targets': list[dict],# the databases opened
                'proposed': list[dict],# the KPIs a derive turn would record
                'added': list,        # triples added, or rows added by a database edit
                'removed': list,      # the same, removed
                'applied': bool,      # whether anything was written
                'error': str | None,  # why a turn could not be served
                'history': list,      # `history` with this turn appended
                'schema': dict,       # the schema to pass to the next turn
                'chains': list,       # the chains to pass to the next turn
                'usage': dict,        # tokens and cost for this turn
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If inputs are missing.
            TypeError:   If `history` is not a list, or `confirm` is not callable.
            OSError:     If the model provider could not be reached.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")
        if not message or not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")
        if history is not None and not isinstance(history, list):
            raise TypeError("history must be a list.")
        if confirm is not None and not callable(confirm):
            raise TypeError("confirm must be callable.")

        history = list(history or [])
        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = RDF.SchemaSummary(rdfGraph)
        meter = meter if meter is not None else CostMeter()
        first = len(meter.calls)

        turnResult: Dict[str, Any] = {
            "answer": "", "sparql": "", "sql": "", "rows": [], "targets": [],
            "proposed": [], "added": [], "removed": [], "applied": False, "error": None,
        }

        transcript = Tool.ChatTranscript(history, maxTurns)
        routed = Tool.ChatRoute(llm, transcript, message, meter,
                                Tool.CHAT_TWIN_ROUTER_PROMPT)
        intent, request = routed["intent"], routed["request"]
        if verbose:
            print(f"\n[chat]    {CostMeter.Describe(meter.calls[-1])}")
            print(f"[chat]    {intent}: {request}")

        def finish(result: Dict[str, Any], label: str) -> Dict[str, Any]:
            """Append this turn to the history and hand back the caller's whole state."""
            turn = {"message": message.strip(), "intent": label, "request": request,
                    "answer": result["answer"], "applied": result["applied"]}
            return {**result, "intent": label, "request": request,
                    "history": history + [turn], "schema": schema, "chains": chains,
                    "usage": meter.Total(first)}

        # --- talk -------------------------------------------------------------------------
        if intent == "talk":
            turnResult["answer"] = Tool.ChatReply(
                llm, transcript, message, meter, Tool.CHAT_TABLE_TALK_PROMPT)
            return finish(turnResult, "talk")

        # --- a question about either half -------------------------------------------------
        if intent != "edit":
            try:
                result = Cycle.TwinQueryByPrompt(
                    rdfGraph, request, basePath=basePath, llm=llm, schema=schema,
                    chains=chains, meter=meter, tableName=tableName, notes=notes,
                    maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                    maxDatabases=maxDatabases, verbose=verbose)
            except ValueError as exc:
                turnResult["error"] = str(exc)
                turnResult["answer"] = f"I could not answer that: {exc}"
                return finish(turnResult, "question")
            turnResult.update({
                "answer": result["answer"], "sparql": result["sparql"], "sql": result["sql"],
                "rows": result["rows"], "targets": result["targets"]})
            return finish(turnResult, "question")

        # --- a change ---------------------------------------------------------------------
        editIntent = Tool.TwinEditRoute(llm, request, meter)
        if verbose:
            print(f"[edit]    {CostMeter.Describe(meter.calls[-1])}")
            print(f"[edit]    {editIntent}")

        if editIntent == "graph":
            try:
                result = Cycle.RDFEditByPrompt(
                    rdfGraph, request, llm=llm, schema=schema, vocabulary=vocabulary,
                    meter=meter, maxRepairs=maxRepairs, emptyRetries=emptyRetries,
                    inPlace=False, verbose=verbose)
            except ValueError as exc:
                turnResult["error"] = str(exc)
                turnResult["answer"] = f"I could not make that change: {exc}"
                return finish(turnResult, "edit:graph")

            turnResult.update({"sparql": result["sparql"], "added": result["added"],
                               "removed": result["removed"]})
            if not result["added"] and not result["removed"]:
                turnResult["answer"] = ("That change would leave the graph exactly as it is: "
                                        "nothing in it matches what you described.")
            elif confirm is not None and confirm({
                    "kind": "graph", "request": request, "sparql": result["sparql"],
                    "added": result["added"], "removed": result["removed"]}):
                edited = result["graph"]
                for triple in set(rdfGraph) - set(edited):
                    rdfGraph.remove(triple)
                for triple in set(edited) - set(rdfGraph):
                    rdfGraph.add(triple)
                turnResult["applied"] = True
                schema, chains = RDF.SchemaSummary(rdfGraph), RDF.Chains(rdfGraph)
                turnResult["answer"] = (
                    f"Done: {len(result['added'])} triple(s) added, "
                    f"{len(result['removed'])} removed. The graph now holds "
                    f"{len(rdfGraph)} triples.")
            else:
                turnResult["answer"] = ("Left the graph as it was. The change is described "
                                        "above if you want to ask for it differently.")
            return finish(turnResult, "edit:graph")

        # Both remaining paths need to know WHICH databases the request is about, and that is
        # the query cycle's locator - reused rather than rebuilt, so an edit and a question
        # resolve a building to the same files.
        try:
            located = Cycle.TwinQueryByPrompt(
                rdfGraph, request, basePath=basePath, llm=llm, schema=schema, chains=chains,
                meter=meter, tableName=tableName, notes=notes, maxRepairs=maxRepairs,
                emptyRetries=emptyRetries, rowLimit=rowLimit, maxDatabases=maxDatabases,
                verbose=verbose)
        except ValueError as exc:
            turnResult["error"] = str(exc)
            turnResult["answer"] = f"I could not find the data for that: {exc}"
            return finish(turnResult, f"edit:{editIntent}")

        turnResult.update({"sparql": located["sparql"], "sql": located["sql"],
                           "rows": located["rows"], "targets": located["targets"]})

        # --- change the readings ----------------------------------------------------------
        if editIntent == "readings":
            changes, added, removed, statement = 0, [], [], ""
            for target in located["targets"]:
                try:
                    edit = Cycle.SQLiteEditByPrompt(
                        target["path"], target["table"] or tableName, request, llm=llm,
                        notes=notes, meter=meter, maxRepairs=maxRepairs,
                        emptyRetries=emptyRetries, diffLimit=diffLimit, verbose=verbose)
                except ValueError as exc:
                    turnResult["error"] = str(exc)
                    continue
                statement = statement or edit["sql"]
                changes += edit["changes"]
                added += [{"building": target["ownerLabel"], **row} for row in edit["added"]]
                removed += [{"building": target["ownerLabel"], **row}
                            for row in edit["removed"]]

            turnResult.update({"sql": statement or turnResult["sql"],
                               "added": added, "removed": removed})
            if not changes:
                turnResult["answer"] = ("That change would leave the readings exactly as they "
                                        "are: no row matches what you described.")
            elif confirm is not None and confirm({
                    "kind": "readings", "request": request, "sql": statement,
                    "added": added, "removed": removed, "changes": changes}):
                written, failures = 0, []
                for target in located["targets"]:
                    moved, _a, _r, failure = Observation.SQLiteApplyUpdate(
                        target["path"], target["table"] or tableName, statement,
                        commit=True, diffLimit=0)
                    written += moved
                    if failure:
                        failures.append(f"{target['ownerLabel']}: {failure}")
                turnResult["applied"] = written > 0
                turnResult["error"] = "; ".join(failures) or None
                turnResult["answer"] = (
                    f"Done: {written} row(s) changed across "
                    f"{len(located['targets'])} database(s)."
                    + (f" {len(failures)} would not commit." if failures else ""))
            else:
                turnResult["answer"] = "Left the readings as they were."
            return finish(turnResult, "edit:readings")

        # --- derive: read the databases, write the graph -----------------------------------
        estate = Tool.TwinEstateBlock(rdfGraph, located["targets"])
        plan = Tool.TwinKPIPlan(llm, request, located["rows"], estate, meter, rowLimit)
        if verbose:
            print(f"[agent 5] {CostMeter.Describe(meter.calls[-1])}")
            print(f"[agent 5] plan: {plan['setName']}, "
                  f"{[k['name'] for k in plan['kpis']]}")

        objects, proposed, reason = Tool.TwinKPIObjects(
            rdfGraph, located["targets"], located["rows"], plan, baseIRI)
        turnResult["proposed"] = proposed
        if not objects:
            turnResult["error"] = reason
            turnResult["answer"] = f"I could not work that out: {reason}"
            return finish(turnResult, "edit:derive")

        if confirm is not None and confirm({
                "kind": "derive", "request": request, "proposed": proposed,
                "setName": plan["setName"]}):
            written, failure = Tool.TwinApplyObjects(rdfGraph, objects, baseIRI)
            if failure:
                turnResult["error"] = failure
                turnResult["answer"] = f"The KPIs were computed but not written: {failure}"
                return finish(turnResult, "edit:derive")
            turnResult["applied"] = True
            turnResult["added"] = proposed
            # The graph has grown a class it did not have: the next question must be grounded
            # in a schema that knows eko:KPI exists, or it cannot be asked about
            schema, chains = RDF.SchemaSummary(rdfGraph), RDF.Chains(rdfGraph)
            replaced = sum(1 for entry in proposed if entry.get("replaces") is not None)
            turnResult["answer"] = (
                f"Done: {len(proposed)} KPI(s) recorded on {len(objects)} building(s) as "
                f"'{plan['setName']}'"
                + (f", {replaced} of them replacing a figure already there" if replaced else "")
                + f". The graph now holds {len(rdfGraph)} triples.")
        else:
            turnResult["answer"] = ("Left the graph as it was. The KPIs are listed above if "
                                    "you want them recorded differently.")
        return finish(turnResult, "edit:derive")

    @staticmethod
    def TwinChat(
        rdfGraph=None,
        *,
        basePath: Optional[Union[str, Path]] = None,
        baseIRI: Optional[str] = None,
        llm: Optional["ChatOpenAI"] = None,
        schema: Optional[Dict[str, Any]] = None,
        chains: Optional[List[Dict[str, Any]]] = None,
        vocabulary: Optional[Dict[str, Any]] = None,
        meter: Optional[CostMeter] = None,
        savePath: Optional[Union[str, Path]] = None,
        autoSave: bool = True,
        notes: Optional[str] = None,
        tableName: str = "observations",
        maxTurns: int = 8,
        maxRepairs: int = 3,
        emptyRetries: int = 1,
        rowLimit: int = 100,
        maxDatabases: int = 25,
        silent: bool = False,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Hold a conversation about a whole twin at the terminal - both halves, read and write.

        Cycle.RDFChat's counterpart for a twin, and a loop around Cycle.TwinChatTurn. It
        prints the answers, shows every proposed change and asks before it lands, and keeps
        the history and the schema threaded from one turn to the next.

        What it can do that neither Cycle.RDFChat nor Cycle.SQLiteChat can is the third kind
        of edit: 'work out annual consumption per building and record it as a KPI' reads the
        databases the graph points at, does the arithmetic in Python, and writes KPI nodes
        back onto the buildings. Ask a question afterwards and the answer can come from what
        was just recorded, because the schema is rebuilt when it lands.

        The confirmation shows a different thing for each kind of change, because they are
        different things: a triple diff for a graph edit, a row diff for a database edit, and
        a table of building, KPI, value and unit for a derived one - with the division that
        produced each figure written out beside it.

        A database edit is committed to the file it was rehearsed in. The graph is edited in
        memory and written to `savePath`, which must not be the file the graph was read from.

        The commands, typed at the prompt:

            /help      what can be typed here
            /sparql    the locator, query or update behind the last answer
            /sql       the SQL behind the last answer
            /rows      the readings the last answer was written from
            /targets   the databases the last turn opened
            /kpis      the KPIs the last derive turn proposed
            /history   the conversation as the router sees it
            /schema    the grounding block the model is given
            /cost      what the conversation has cost so far
            /silent    stop showing the query and the cost of each turn, or show them again
            /verbose   show each agent's step and cost, or stop showing them
            /save      write the graph to `savePath`, when autoSave has not
            /exit      leave, /quit does the same

        Args:
            rdfGraph: An rdflib.Graph describing the estate. Edited in place on confirmation.
            basePath: The directory the graph's file paths are relative to.
            baseIRI: The base the graph's identifiers were minted with.
            llm: A chat model from LLM.Constructor. Built here when not supplied.
            schema: The output of RDF.SchemaSummary, kept current across edits.
            chains: The output of RDF.Chains, kept current the same way.
            vocabulary: The output of Tool.JSONLDVocabulary, built once here.
            meter: A CostMeter to tally token usage and cost into.
            savePath: Where the edited graph is written. Must not be the file it was read
                from: an edit is the model's work, and overwriting the source would leave
                nothing to compare it against. Without a path nothing is ever written and an
                edited graph lives only as long as the session.
            autoSave: Write `savePath` as soon as a graph edit lands, rather than waiting for
                /save. On by default, so a session cannot end with confirmed edits lost.
            notes: Domain context for the SQL half.
            tableName: The table to read in a database whose graph entry does not name one.
            maxTurns: How many past turns the router is shown.
            maxRepairs: How many times a rejected query or statement may be sent back.
            emptyRetries: How many times an empty result is rewritten.
            rowLimit: Maximum rows a generated query may return, per database.
            maxDatabases: Refuse a fan-out wider than this.
            silent: Print the answers and nothing else. /silent toggles it.
            verbose: Start with the per-agent narration on. /verbose toggles it.

        Returns:
            dict: {
                'history': list,   # every turn taken
                'graph': Graph,    # the graph, edited where edits were confirmed
                'schema': dict,    # the schema as it stands at the end
                'chains': list,    # the chains as they stand at the end
                'edits': int,      # how many changes were applied
                'saved': bool,     # whether the graph on disk matches the graph in memory
                'usage': dict,     # tokens and cost for the whole conversation
            }

        Raises:
            ImportError: If `rdflib` or `langchain-openai` is not installed.
            ValueError:  If `rdfGraph` is missing.
        """
        if rdfGraph is None:
            raise ValueError("rdfGraph must be provided.")

        llm = llm if llm is not None else LLM.Constructor()
        if schema is None:
            schema = RDF.SchemaSummary(rdfGraph)
        vocabulary = vocabulary if vocabulary is not None else Tool.JSONLDVocabulary()
        meter = meter if meter is not None else CostMeter()

        history: List[Dict[str, Any]] = []
        lastResult: Optional[Dict[str, Any]] = None
        edits, unsaved = 0, False

        def confirm(proposal: Dict[str, Any]) -> bool:
            """
            Show the change and ask. Three shapes, because they are three different changes.

            A model-written update is never applied unseen, and 'seen' has to mean the thing
            that will actually happen: triples for a graph edit, rows for a database edit,
            and for a derived KPI the arithmetic itself - the divisor included, so a figure
            that looks wrong can be traced without leaving the prompt.
            """
            kind = proposal.get("kind")
            if kind == "derive":
                replaced = [e for e in proposal["proposed"] if e.get("replaces") is not None]
                print(f"\n  it would record '{proposal['setName']}'"
                      + (f", replacing {len(replaced)} figure(s) already there:"
                         if replaced else ":"))
                for entry in proposal["proposed"]:
                    divided = f"  ({entry['from']} / {entry['dividedBy']})" \
                        if entry["dividedBy"] else f"  ({entry['from']})"
                    # An overwrite shows what it overwrites: agreeing to replace 57.99 with
                    # 61.20 is a different decision from agreeing to record 61.20
                    was = (f"  was {entry['replaces']}"
                           if entry.get("replaces") is not None else "")
                    print(f"    {entry['building']:<26}{entry['kpi']:<28}"
                          f"{entry['value']:>12,.4g} {entry['unit'] or ''}{divided}{was}")
            elif kind == "readings":
                print(f"\n  the change it proposes ({proposal['changes']} row(s)):")
                for row in proposal["removed"][:8]:
                    print(f"    - {row}")
                for row in proposal["added"][:8]:
                    print(f"    + {row}")
            else:
                print("\n  the change it proposes:")
                for triple in proposal["removed"]:
                    print(f"    - {' '.join(triple)}")
                for triple in proposal["added"]:
                    print(f"    + {' '.join(triple)}")
            try:
                reply = _ReadLine("  apply? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                # Ctrl-C at the confirmation refuses the change; it does not end the session
                print()
                return False
            return reply is not None and reply.strip().lower() in ("y", "yes")

        print(f"\nChatting about a twin of {len(rdfGraph)} triples, via {llm.model_name}.")
        print("Ask about the estate, about the readings, or about both. Describe a change to")
        print("either - including 'work out X per building and record it'.")
        print("/help for commands, Esc or /exit to leave.\n")

        while True:
            try:
                line = _ReadLine("you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line is None:            # Escape
                break
            message = line.strip()
            if not message:
                continue

            if message.startswith("/"):
                command = message.split()[0].lower()
                if command in ("/exit", "/quit"):
                    break
                elif command == "/help":
                    print("  /sparql  /sql  /rows  /targets  /kpis  /history  /schema")
                    print("  /cost  /silent  /verbose  /save  /exit")
                    print("  Esc leaves too, and answers no to a change.")
                elif command in ("/sparql", "/sql"):
                    key = "sparql" if command == "/sparql" else "sql"
                    print(f"\n{(lastResult or {}).get(key) or '(nothing behind that answer)'}\n")
                elif command == "/rows":
                    for row in (lastResult or {}).get("rows", [])[:20] or ["  no rows"]:
                        print(f"    {row}")
                elif command == "/targets":
                    for target in (lastResult or {}).get("targets", []) or ["  none"]:
                        print(f"    {target}")
                elif command == "/kpis":
                    for entry in (lastResult or {}).get("proposed", []) or ["  none"]:
                        print(f"    {entry}")
                elif command == "/history":
                    print(f"\n{Tool.ChatTranscript(history, maxTurns)}\n")
                elif command == "/schema":
                    print(f"\n{schema['text']}\n")
                elif command == "/cost":
                    total = meter.Total()
                    print(f"  {total['calls']} call(s), {CostMeter.Describe(total)}")
                elif command == "/silent":
                    silent = not silent
                    print(f"  silent {'on' if silent else 'off'}")
                elif command == "/verbose":
                    verbose = not verbose
                    print(f"  verbose {'on' if verbose else 'off'}")
                elif command == "/save":
                    if savePath is None:
                        print("  no savePath was given, so there is nowhere to write")
                    else:
                        rdfGraph.serialize(destination=str(savePath), format="turtle")
                        unsaved = False
                        print(f"  written to {savePath}")
                else:
                    print(f"  no such command: {command}. /help lists them.")
                continue

            try:
                lastResult = Cycle.TwinChatTurn(
                    rdfGraph, message, basePath=basePath, baseIRI=baseIRI, history=history,
                    llm=llm, schema=schema, chains=chains, vocabulary=vocabulary, meter=meter,
                    confirm=confirm, notes=notes, tableName=tableName, maxTurns=maxTurns,
                    maxRepairs=maxRepairs, emptyRetries=emptyRetries, rowLimit=rowLimit,
                    maxDatabases=maxDatabases, verbose=verbose)
            except OSError as exc:
                # The remote model is unreachable: every following turn would fail the same way
                print(f"\n{exc}\n")
                break

            history, schema = lastResult["history"], lastResult["schema"]
            chains = lastResult["chains"]
            saveNote = ""
            if lastResult["applied"]:
                edits += 1
                # A database edit was committed to its own file; only a graph edit is in
                # memory and therefore only a graph edit has anything to save
                if lastResult["intent"] in ("edit:graph", "edit:derive"):
                    unsaved = True
                    if autoSave and savePath is not None:
                        try:
                            rdfGraph.serialize(destination=str(savePath), format="turtle")
                            unsaved = False
                            saveNote = f"     saved to {Path(savePath).name}"
                        except OSError as exc:
                            saveNote = f"     could not write {Path(savePath).name}: {exc}"

            print(f"\nbot> {lastResult['answer']}")
            if saveNote:
                print(saveNote)
            if not silent:
                if lastResult["targets"]:
                    names = ", ".join(
                        f"{t['ownerLabel'] or t['owner']} ({t['property'] or '?'})"
                        for t in lastResult["targets"])
                    print(f"\n     {len(lastResult['targets'])} database(s): {names}")
                for label in ("sparql", "sql"):
                    if lastResult[label]:
                        print(f"\n     the {label} it ran:")
                        for text in lastResult[label].splitlines():
                            print(f"       {text}")
                running = meter.Total()
                print(f"\n     this turn: {lastResult['usage']['calls']} call(s), "
                      f"{CostMeter.Describe(lastResult['usage'])}")
                print(f"     so far:    {running['calls']} call(s), "
                      f"{CostMeter.Describe(running)}")
            print()

        if unsaved:
            print(f"{edits} edit(s) include graph changes held in memory only. /save writes "
                  f"them" + (f" to {savePath}." if savePath else ", once a savePath is given."))
        elif edits:
            print(f"{edits} edit(s) applied.")

        total = meter.Total()
        if not silent:
            print(f"\nConversation: {len(history)} turn(s), {total['calls']} call(s), "
                  f"{CostMeter.Describe(total)}")

        return {
            "history": history,
            "graph": rdfGraph,
            "schema": schema,
            "chains": chains,
            "edits": edits,
            "saved": not unsaved,
            "usage": total,
        }

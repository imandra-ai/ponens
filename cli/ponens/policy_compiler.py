#!/usr/bin/env python3
"""
Policy Compiler: Formula → IML

Parses LTL-based policy formulas from trace JSON and generates IML source
code using the policy_combinators.iml combinator library.

Usage:
    python policy_compiler.py trace_v1_1.json > policies_generated.iml
    python policy_compiler.py trace_v1_1.json --ast   # show parse trees
"""

import json
import sys
from dataclasses import dataclass
from typing import Union

# ================================================================
# AST
# ================================================================

@dataclass
class Globally:
    body: 'Formula'

@dataclass
class Finally:
    body: 'Formula'

@dataclass
class Next:
    body: 'Formula'

@dataclass
class Previously:
    body: 'Formula'

@dataclass
class Historically:
    body: 'Formula'

@dataclass
class PTarget:
    body: 'Formula'

@dataclass
class PChain:
    body: 'Formula'

@dataclass
class Until:
    left: 'Formula'
    right: 'Formula'

@dataclass
class Since:
    left: 'Formula'
    right: 'Formula'

@dataclass
class SinceLast:
    left: 'Formula'
    right: 'Formula'

@dataclass
class Implies:
    left: 'Formula'
    right: 'Formula'

@dataclass
class And:
    left: 'Formula'
    right: 'Formula'

@dataclass
class Or:
    left: 'Formula'
    right: 'Formula'

@dataclass
class Not:
    body: 'Formula'

@dataclass
class Atom:
    """Action type, artifact type, category, or predicate name."""
    name: str

@dataclass
class FieldNeEmpty:
    """field != empty"""
    field: str

@dataclass
class AtomWithArgs:
    """e.g., VerificationResult(proved | sat)"""
    name: str
    args: list['Formula']

@dataclass
class StartEvent:
    pass

@dataclass
class EndEvent:
    pass

@dataclass
class MemberOf:
    """elem in set_expr"""
    elem: 'Formula'
    set_expr: 'Formula'

@dataclass
class Ancestors:
    """ancestors(derived_from)"""
    field: str

@dataclass
class SetComprehension:
    """{ expr | condition }"""
    expr: str
    condition: 'Formula'

@dataclass
class SetLiteral:
    """{a.id | a.type = T}"""
    description: str

@dataclass
class Equals:
    left: 'Formula'
    right: 'Formula'

@dataclass
class ForAll:
    var: str
    set_name: str
    body: 'Formula'

@dataclass
class Exists:
    var: str
    set_name: str
    body: 'Formula'

@dataclass
class ExistsUnique:
    var: str
    set_name: str
    body: 'Formula'

@dataclass
class LessThan:
    left: str
    right: str

@dataclass
class FieldAccess:
    """field access on a bound quantifier variable: r.severity, r.status, ..."""
    var: str
    field: str

@dataclass
class Compare:
    """comparison of a field access against a value: r.severity >= High, r.kind = Assumption."""
    left: 'Formula'   # FieldAccess
    op: str           # '=', '!=', '>=', '>', '<=', '<'
    right: 'Formula'  # Atom (value name) or Atom('EMPTY')

@dataclass
class FuncApp:
    """function application: inputs(a), outputs(b), target(a)"""
    func: str
    arg: str

@dataclass
class RawStructural:
    """Structural formula that doesn't parse into pure temporal LTL.
    Emitted as a comment + reference to hand-written combinator."""
    original: str
    policy_name: str

Formula = Union[
    Globally, Finally, Next, Previously, Historically,
    PTarget, PChain, Until, Since, SinceLast,
    Implies, And, Or, Not,
    Atom, FieldNeEmpty, AtomWithArgs, StartEvent, EndEvent,
    MemberOf, Ancestors, SetComprehension, SetLiteral,
    Equals, ForAll, Exists, ExistsUnique, LessThan, FuncApp,
    FieldAccess, Compare,
    RawStructural,
]


# ================================================================
# Tokenizer
# ================================================================

# Known action types and artifact types
ACTION_TYPES = {
    'EditFile', 'ReadFile', 'ReadDocumentation', 'SearchCode', 'AnalyzeCode',
    'CreateFile', 'DeleteFile', 'RenameFile',
    'RunTests', 'TypeCheck', 'Lint', 'ManualVerification',
    'RunCommand', 'ExploreDirectory',
    'GitCommit', 'GitStatus', 'GitDiff',
    'AskUser', 'ReportProgress', 'Explain',
    'FormulatePlan', 'DecomposeTask', 'EstimateImpact',
    'Formalize', 'DefineVG', 'Verify', 'Decompose', 'GenerateTests',
}

ARTIFACT_TYPES = {
    'SourceCode', 'Documentation', 'SearchResults', 'AnalysisNote', 'Plan',
    'Formalization', 'IMLModel', 'VerificationGoal', 'VerificationResult',
    'Decomposition', 'GeneratedTests',
    'CommandResult', 'Diff', 'Commit', 'UserApproval', 'UserInstruction',
}

TEMPORAL_OPS = {'G', 'F', 'X', 'P', 'H', 'U', 'S'}
SCOPED_OPS = {'P_target', 'P_chain', 'H_target', 'H_chain', 'S_last'}
PREDICATES = {
    'completed', 'failed', 'proved', 'refuted', 'sat', 'unknown',
    'action', 'gateway', 'reasoning', 'activity',
    'start_event', 'end_event', 'high_stakes_path',
}
FIELDS = {
    'rationale', 'target_artifact_id', 'files_modified',
    'inputs', 'outputs', 'target', 'ancestors', 'derived_from',
    'ref_model',
}

# Unicode to ASCII mapping for tokenizer
UNICODE_MAP = {
    '\u2192': '->', '\u2227': '&&', '\u2228': '||', '\u00ac': '!',
    '\u2200': 'FORALL', '\u2203': 'EXISTS',
    '\u2208': 'IN', '\u2260': '!=', '\u2205': 'EMPTY',
    '\u2265': '>=', '\u2264': '<=',
}

@dataclass
class Token:
    kind: str  # 'IDENT', 'OP', 'LPAREN', 'RPAREN', 'LBRACE', 'RBRACE', 'DOT', 'COMMA', 'PIPE', 'EOF'
    value: str
    pos: int


def tokenize(formula: str) -> list[Token]:
    tokens = []
    i = 0
    n = len(formula)

    while i < n:
        c = formula[i]

        # Skip whitespace
        if c in ' \t\n\r':
            i += 1
            continue

        # Unicode operators
        if c in UNICODE_MAP:
            val = UNICODE_MAP[c]
            # Check for exists-unique: ∃!
            if c == '\u2203' and i + 1 < n and formula[i + 1] == '!':
                tokens.append(Token('OP', 'EXISTS_UNIQUE', i))
                i += 2
                continue
            tokens.append(Token('OP', val, i))
            i += 1
            continue

        # Parentheses and braces
        if c == '(':
            tokens.append(Token('LPAREN', '(', i))
            i += 1
            continue
        if c == ')':
            tokens.append(Token('RPAREN', ')', i))
            i += 1
            continue
        if c == '{':
            tokens.append(Token('LBRACE', '{', i))
            i += 1
            continue
        if c == '}':
            tokens.append(Token('RBRACE', '}', i))
            i += 1
            continue

        # Dot
        if c == '.':
            tokens.append(Token('DOT', '.', i))
            i += 1
            continue

        # Comma
        if c == ',':
            tokens.append(Token('COMMA', ',', i))
            i += 1
            continue

        # ASCII digraphs: ->, &&, ||
        if c == '-' and i + 1 < n and formula[i + 1] == '>':
            tokens.append(Token('OP', '->', i))
            i += 2
            continue
        if c == '&' and i + 1 < n and formula[i + 1] == '&':
            tokens.append(Token('OP', '&&', i))
            i += 2
            continue

        # Pipe: || (ASCII or) or single |
        if c == '|':
            if i + 1 < n and formula[i + 1] == '|':
                tokens.append(Token('OP', '||', i))
                i += 2
            else:
                tokens.append(Token('PIPE', '|', i))
                i += 1
            continue

        # Equals
        if c == '=':
            tokens.append(Token('OP', '=', i))
            i += 1
            continue

        # Less than / greater than (and <=, >=)
        if c == '<':
            if i + 1 < n and formula[i + 1] == '=':
                tokens.append(Token('OP', '<=', i)); i += 2
            else:
                tokens.append(Token('OP', '<', i)); i += 1
            continue
        if c == '>':
            if i + 1 < n and formula[i + 1] == '=':
                tokens.append(Token('OP', '>=', i)); i += 2
            else:
                tokens.append(Token('OP', '>', i)); i += 1
            continue

        # Exclamation (NOT or EXISTS_UNIQUE part)
        if c == '!':
            if i + 1 < n and formula[i + 1] == '=':
                tokens.append(Token('OP', '!=', i))
                i += 2
            else:
                tokens.append(Token('OP', '!', i))
                i += 1
            continue

        # Identifiers and keywords
        if c.isalpha() or c == '_':
            start = i
            while i < n and (formula[i].isalnum() or formula[i] == '_'):
                i += 1
            word = formula[start:i]
            tokens.append(Token('IDENT', word, start))
            continue

        # Skip unknown
        i += 1

    tokens.append(Token('EOF', '', n))
    return tokens


# ================================================================
# Parser (recursive descent)
# ================================================================

class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token], original: str, policy_name: str = ''):
        self.tokens = tokens
        self.pos = 0
        self.original = original
        self.policy_name = policy_name

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, kind: str, value: str = None) -> Token:
        t = self.advance()
        if t.kind != kind or (value is not None and t.value != value):
            raise ParseError(f"Expected {kind}:{value}, got {t.kind}:{t.value} at pos {t.pos}")
        return t

    def at(self, kind: str, value: str = None) -> bool:
        t = self.peek()
        if t.kind != kind:
            return False
        if value is not None and t.value != value:
            return False
        return True

    def parse(self) -> Formula:
        """Entry point: parse a full formula."""
        try:
            result = self.parse_implies()
            return result
        except ParseError:
            # Fall back to structural for complex formulas
            return RawStructural(self.original, self.policy_name)

    def parse_implies(self) -> Formula:
        left = self.parse_or()
        while self.at('OP', '->'):
            self.advance()
            right = self.parse_or()
            left = Implies(left, right)
        return left

    def parse_or(self) -> Formula:
        left = self.parse_and()
        while self.at('OP', '||'):
            self.advance()
            right = self.parse_and()
            left = Or(left, right)
        return left

    def parse_and(self) -> Formula:
        left = self.parse_binary_temporal()
        while self.at('OP', '&&'):
            self.advance()
            right = self.parse_binary_temporal()
            left = And(left, right)
        return left

    def parse_binary_temporal(self) -> Formula:
        """Handle binary temporal operators: U, S, S_last"""
        left = self.parse_unary()

        while True:
            if self.at('IDENT', 'U'):
                self.advance()
                right = self.parse_unary()
                left = Until(left, right)
            elif self.at('IDENT', 'S_last'):
                self.advance()
                right = self.parse_unary()
                left = SinceLast(left, right)
            elif self.at('IDENT', 'S') and not self._is_scoped_op('S'):
                self.advance()
                right = self.parse_unary()
                left = Since(left, right)
            else:
                break

        return left

    def _is_scoped_op(self, prefix: str) -> bool:
        """Check if current S is actually S_last etc."""
        if self.pos + 1 < len(self.tokens):
            next_t = self.tokens[self.pos + 1]
            if next_t.kind == 'IDENT' and next_t.value.startswith('_'):
                return True
        return False

    def parse_unary(self) -> Formula:
        t = self.peek()

        # NOT
        if t.kind == 'OP' and t.value == '!':
            self.advance()
            body = self.parse_unary()
            return Not(body)

        # Temporal unary operators
        if t.kind == 'IDENT' and t.value == 'G':
            self.advance()
            body = self.parse_primary()
            return Globally(body)

        if t.kind == 'IDENT' and t.value == 'F':
            self.advance()
            body = self.parse_primary()
            return Finally(body)

        if t.kind == 'IDENT' and t.value == 'X':
            self.advance()
            body = self.parse_primary()
            return Next(body)

        if t.kind == 'IDENT' and t.value == 'P_target':
            self.advance()
            body = self.parse_primary()
            return PTarget(body)

        if t.kind == 'IDENT' and t.value == 'P_chain':
            self.advance()
            body = self.parse_primary()
            return PChain(body)

        if t.kind == 'IDENT' and t.value == 'H_target':
            self.advance()
            body = self.parse_primary()
            return Historically(body)  # TODO: scoped

        if t.kind == 'IDENT' and t.value == 'H_chain':
            self.advance()
            body = self.parse_primary()
            return Historically(body)  # TODO: scoped

        if t.kind == 'IDENT' and t.value == 'P':
            self.advance()
            body = self.parse_primary()
            return Previously(body)

        if t.kind == 'IDENT' and t.value == 'H':
            self.advance()
            body = self.parse_primary()
            return Historically(body)

        # Quantifiers
        if t.kind == 'OP' and t.value == 'FORALL':
            return self.parse_forall()

        if t.kind == 'OP' and t.value in ('EXISTS', 'EXISTS_UNIQUE'):
            return self.parse_exists()

        return self.parse_primary()

    def parse_primary(self) -> Formula:
        t = self.peek()

        # Parenthesized expression
        if t.kind == 'LPAREN':
            self.advance()
            expr = self.parse_implies()
            self.expect('RPAREN')
            return expr

        # Set literal { ... | ... }
        if t.kind == 'LBRACE':
            return self.parse_set_literal()

        # Identifiers
        if t.kind == 'IDENT':
            return self.parse_ident_expr()

        raise ParseError(f"Unexpected token {t.kind}:{t.value} at pos {t.pos}")

    def parse_ident_expr(self) -> Formula:
        t = self.advance()
        name = t.value

        # start_event / end_event
        if name == 'start_event':
            return StartEvent()
        if name == 'end_event':
            return EndEvent()

        # field access on a bound variable: r.severity = Critical, r.suggested_check != EMPTY
        if self.at('DOT'):
            self.advance()
            field = self.advance().value
            left = FieldAccess(name, field)
            for op in ('!=', '>=', '<=', '=', '>', '<'):
                if self.at('OP', op):
                    self.advance()
                    return Compare(left, op, self._parse_value())
            return left

        # field != empty
        if self.at('OP', '!='):
            self.advance()
            if self.at('OP', 'EMPTY') or self.at('IDENT', 'EMPTY'):
                self.advance()
                return FieldNeEmpty(name)
            raise ParseError(f"Expected EMPTY after !=")

        # field = set_expr
        if self.at('OP', '=') and name in FIELDS:
            self.advance()
            if self.at('LBRACE'):
                set_expr = self.parse_set_literal()
                return Equals(Atom(name), set_expr)
            right = self.parse_primary()
            return Equals(Atom(name), right)

        # field IN set_expr
        if self.at('OP', 'IN'):
            self.advance()
            set_expr = self.parse_primary()
            return MemberOf(Atom(name), set_expr)

        # function application: name(arg)
        if self.at('LPAREN') and name in FIELDS:
            self.advance()
            arg = self.advance()
            self.expect('RPAREN')
            return FuncApp(name, arg.value)

        # Atom with args: VerificationResult(proved || sat)
        if self.at('LPAREN') and (name in ARTIFACT_TYPES or name in ACTION_TYPES):
            self.advance()
            args = [self.parse_implies()]
            while self.at('OP', '||') or self.at('COMMA'):
                self.advance()
                args.append(self.parse_implies())
            self.expect('RPAREN')
            return AtomWithArgs(name, args)

        # ancestors(derived_from)
        if name == 'ancestors' and self.at('LPAREN'):
            self.advance()
            field = self.advance().value
            self.expect('RPAREN')
            return Ancestors(field)

        # Plain atom
        return Atom(name)

    def parse_set_literal(self) -> Formula:
        """Parse { expr | condition } or { a.id | a.type = T }"""
        self.expect('LBRACE')
        # Collect everything until }
        depth = 1
        parts = []
        while depth > 0:
            t = self.advance()
            if t.kind == 'LBRACE':
                depth += 1
            elif t.kind == 'RBRACE':
                depth -= 1
                if depth == 0:
                    break
            parts.append(t.value)
        return SetLiteral(' '.join(parts))

    def _parse_value(self) -> Formula:
        """Parse the right-hand side of a field comparison: a value name or EMPTY."""
        if self.at('OP', 'EMPTY') or self.at('IDENT', 'EMPTY'):
            self.advance()
            return Atom('EMPTY')
        return Atom(self.advance().value)

    def _quant_separator(self):
        """A quantifier body is separated by '.' (math) or '->' (implication sugar)."""
        if self.at('DOT'):
            self.advance()
        elif self.at('OP', '->'):
            self.advance()
        else:
            t = self.peek()
            raise ParseError(f"Expected '.' or '->' after quantifier set, got {t.kind}:{t.value} at pos {t.pos}")

    def parse_forall(self) -> Formula:
        self.advance()  # FORALL
        var = self.advance().value
        self.expect('OP', 'IN')
        set_name = self.parse_func_or_ident()
        self._quant_separator()
        body = self.parse_implies()
        return ForAll(var, set_name, body)

    def parse_exists(self) -> Formula:
        t = self.advance()  # EXISTS or EXISTS_UNIQUE
        is_unique = t.value == 'EXISTS_UNIQUE'
        var = self.advance().value
        set_name = ''
        if self.at('OP', 'IN'):
            self.advance()
            set_name = self.parse_func_or_ident()
        self._quant_separator()
        body = self.parse_implies()
        if is_unique:
            return ExistsUnique(var, set_name, body)
        return Exists(var, set_name, body)

    def parse_func_or_ident(self) -> str:
        name = self.advance().value
        if self.at('LPAREN'):
            self.advance()
            arg = self.advance().value
            self.expect('RPAREN')
            return f"{name}({arg})"
        return name


# ================================================================
# IML Code Generator
# ================================================================

def to_iml_action_type(name: str) -> str:
    """Convert an action type name to IML constructor."""
    return name


def to_iml_artifact_type(name: str) -> str:
    """Convert artifact type name to IML constructor, avoiding clashes."""
    remap = {
        'Formalization': 'Formalization_Art',
        'Decomposition': 'Decomposition_Art',
        'GeneratedTests': 'GeneratedTests_Art',
    }
    return remap.get(name, name)


def gen_iml(node: Formula, var: str = 'a') -> str:
    """
    Generate IML expression from AST.
    var = current action variable name ('a' at top level, 'b' inside temporal operators).
    """
    match node:
        case Globally(body):
            inner = gen_iml(body, 'a')
            return f"globally (fun a t ->\n    {inner}\n  ) t"

        case Finally(body):
            inner = gen_iml(body, 'a')
            return f"finally_ (fun a t ->\n    {inner}\n  ) t"

        case Previously(body):
            inner = gen_iml(body, 'b')
            return f"previously (fun b t -> {inner}) {var} t"

        case Historically(body):
            inner = gen_iml(body, 'b')
            return f"historically (fun b t -> {inner}) {var} t"

        case PTarget(body):
            inner = gen_iml(body, 'b')
            return f"p_target (fun b t -> {inner}) {var} t"

        case PChain(body):
            inner = gen_iml(body, 'b')
            return f"p_chain (fun b t -> {inner}) {var} t"

        case SinceLast(left, right):
            l = gen_iml(left, 'b')
            r = gen_iml(right, 'b')
            return f"s_last (fun b t -> {l}) (fun b t -> {r}) {var} t"

        case Since(left, right):
            l = gen_iml(left, 'b')
            r = gen_iml(right, 'b')
            return f"since (fun b t -> {l}) (fun b t -> {r}) {var} t"

        case Until(left, right):
            l = gen_iml(left, var)
            r = gen_iml(right, var)
            return f"(* Until: {l} U {r} — requires custom implementation *)"

        case Implies(left, right):
            l = gen_iml(left, var)
            r = gen_iml(right, var)
            return f"(not ({l})) || ({r})"

        case And(left, right):
            l = gen_iml(left, var)
            r = gen_iml(right, var)
            return f"({l}) && ({r})"

        case Or(left, right):
            l = gen_iml(left, var)
            r = gen_iml(right, var)
            return f"({l}) || ({r})"

        case Not(body):
            inner = gen_iml(body, var)
            return f"not ({inner})"

        case Atom(name):
            if name in ACTION_TYPES:
                return f"{var}.action_type = {to_iml_action_type(name)}"
            if name in ARTIFACT_TYPES:
                return f"{var}.artifact_type = {to_iml_artifact_type(name)}"
            if name in ('gateway', 'reasoning', 'activity'):
                return f"{var}.category = {name.capitalize()}"
            if name == 'action':
                return 'true'  # every position is an action
            if name in PREDICATES:
                if name in ('completed', 'failed'):
                    return f"{var}.result_status = Some {name.capitalize()}"
                if name in ('proved', 'refuted', 'sat'):
                    return f"{var}.result_status = Some {name.capitalize()}"
                if name == 'high_stakes_path':
                    return f'is_high_stakes_path (target_of {var})'
                return name
            return name

        case AtomWithArgs(name, args):
            type_name = to_iml_artifact_type(name) if name in ARTIFACT_TYPES else to_iml_action_type(name)
            if len(args) == 1 and isinstance(args[0], Or):
                statuses = collect_or_atoms(args[0])
                status_checks = ' || '.join(
                    f"{var}.result_status = Some {s.name.capitalize()}" if isinstance(s, Atom) else gen_iml(s, var)
                    for s in statuses
                )
                if name in ARTIFACT_TYPES:
                    return f"({var}.artifact_type = {type_name} && ({status_checks}))"
                return f"({var}.action_type = {type_name} && ({status_checks}))"
            inner = ' && '.join(gen_iml(a, var) for a in args)
            if name in ARTIFACT_TYPES:
                return f"({var}.artifact_type = {type_name} && {inner})"
            return f"({var}.action_type = {type_name} && {inner})"

        case FieldNeEmpty(field):
            return f'String.length {var}.{field} > 0'

        case StartEvent():
            return 'is_start_event t.trigger'

        case EndEvent():
            return 'is_end_event t.outcome'

        case MemberOf(elem, set_expr):
            e = gen_iml(elem, var)
            s = gen_iml(set_expr, var)
            return f"(* {e} IN {s} — structural, see combinator library *)"

        case Ancestors(field):
            return f"ancestors({field})"

        case SetLiteral(description):
            return f"(* set: {{{description}}} — structural, see combinator library *)"

        case RawStructural(original, policy_name):
            return f"(* Structural formula — use hand-written combinator:\n     {original} *)\n  {policy_name} t"

        case ForAll(var_name, set_name, body):
            inner = gen_iml(body, var)
            return f"(* forall {var_name} in {set_name}: {inner} — structural *)"

        case Equals(left, right):
            l = gen_iml(left, var)
            r = gen_iml(right, var)
            return f"(* {l} = {r} — structural, see combinator library *)"

        case _:
            return f"(* unhandled: {node} *)"


def collect_or_atoms(node: Formula) -> list[Formula]:
    """Flatten nested Or into a list."""
    if isinstance(node, Or):
        return collect_or_atoms(node.left) + collect_or_atoms(node.right)
    return [node]


# ================================================================
# Policy classification
# ================================================================

STRUCTURAL_POLICIES = {
    'data_flow_integrity',
    'goals_reference_valid_artifacts',
    'files_modified_consistent',
    'generated_tests_require_decomposition',
    # residual surface policies (quantify over trace.residuals — see Trace Spec §13)
    'no_open_critical_residuals',
    'high_severity_residuals_acknowledged_before_commit',
    'unverified_residuals_have_suggested_check',
    'assumptions_are_located',
}


def classify_formula(name: str, ast: Formula) -> str:
    """Classify a policy as pure_temporal, scoped_temporal, or structural."""
    if name in STRUCTURAL_POLICIES:
        return 'structural'
    if contains_scoped(ast):
        return 'scoped_temporal'
    return 'pure_temporal'


def contains_scoped(node: Formula) -> bool:
    match node:
        case PTarget(_) | PChain(_) | SinceLast(_, _):
            return True
        case Globally(body) | Finally(body) | Next(body) | Previously(body) | Historically(body) | Not(body):
            return contains_scoped(body)
        case Implies(l, r) | And(l, r) | Or(l, r) | Until(l, r) | Since(l, r):
            return contains_scoped(l) or contains_scoped(r)
        case _:
            return False


# ================================================================
# Syntax and semantic checker
# ================================================================

@dataclass
class CheckError:
    message: str
    path: str  # e.g. "G > Implies > PTarget > Atom"

@dataclass
class CheckWarning:
    message: str
    path: str


VALID_ATOMS = ACTION_TYPES | ARTIFACT_TYPES | PREDICATES | FIELDS | {
    'action', 'gateway', 'reasoning', 'activity',
    'start_event', 'end_event', 'high_stakes_path',
    'completed', 'failed', 'proved', 'refuted', 'sat', 'unknown',
}


def check_formula(node: Formula, policy_name: str) -> tuple[list[CheckError], list[CheckWarning]]:
    """Validate a parsed formula for syntax and semantic correctness."""
    errors: list[CheckError] = []
    warnings: list[CheckWarning] = []

    def walk(node: Formula, path: str, inside_temporal: bool, inside_global: bool):
        match node:
            case Globally(body):
                if inside_global:
                    warnings.append(CheckWarning("Nested G (globally) — usually redundant on finite traces", path))
                walk(body, f"{path} > G", inside_temporal, True)

            case Finally(body):
                walk(body, f"{path} > F", inside_temporal, inside_global)

            case Next(body):
                warnings.append(CheckWarning("X (next) is rarely useful in trace policies — consider P or F", path))
                walk(body, f"{path} > X", inside_temporal, inside_global)

            case Previously(body):
                if not inside_global:
                    warnings.append(CheckWarning("P (previously) outside G — applies only at trace start", path))
                walk(body, f"{path} > P", True, inside_global)

            case Historically(body):
                if not inside_global:
                    warnings.append(CheckWarning("H (historically) outside G — applies only at trace start", path))
                walk(body, f"{path} > H", True, inside_global)

            case PTarget(body):
                if not inside_global:
                    warnings.append(CheckWarning("P_target outside G — applies only at trace start", path))
                walk(body, f"{path} > P_target", True, inside_global)

            case PChain(body):
                if not inside_global:
                    warnings.append(CheckWarning("P_chain outside G — applies only at trace start", path))
                walk(body, f"{path} > P_chain", True, inside_global)

            case SinceLast(left, right):
                if not inside_global:
                    warnings.append(CheckWarning("S_last outside G — applies only at trace start", path))
                walk(left, f"{path} > S_last.left", True, inside_global)
                walk(right, f"{path} > S_last.right", True, inside_global)

            case Since(left, right):
                walk(left, f"{path} > S.left", True, inside_global)
                walk(right, f"{path} > S.right", True, inside_global)

            case Until(left, right):
                walk(left, f"{path} > U.left", inside_temporal, inside_global)
                walk(right, f"{path} > U.right", inside_temporal, inside_global)

            case Implies(left, right):
                walk(left, f"{path} > Implies.left", inside_temporal, inside_global)
                walk(right, f"{path} > Implies.right", inside_temporal, inside_global)

            case And(left, right):
                walk(left, f"{path} > And.left", inside_temporal, inside_global)
                walk(right, f"{path} > And.right", inside_temporal, inside_global)

            case Or(left, right):
                walk(left, f"{path} > Or.left", inside_temporal, inside_global)
                walk(right, f"{path} > Or.right", inside_temporal, inside_global)

            case Not(body):
                walk(body, f"{path} > Not", inside_temporal, inside_global)

            case Atom(name):
                if name not in VALID_ATOMS and name not in ('a', 'b', 't'):
                    warnings.append(CheckWarning(
                        f"Custom predicate '{name}' — not a standard atom; will be matched as a keyword against action text",
                        path
                    ))

            case AtomWithArgs(name, args):
                if name not in ACTION_TYPES and name not in ARTIFACT_TYPES:
                    errors.append(CheckError(
                        f"Unknown type '{name}' in parameterized atom — not a recognized action or artifact type",
                        path
                    ))
                for i, arg in enumerate(args):
                    walk(arg, f"{path} > {name}.arg{i}", inside_temporal, inside_global)

            case FieldNeEmpty(field):
                if field not in FIELDS and field not in ('rationale', 'description', 'label', 'detail'):
                    warnings.append(CheckWarning(f"Field '{field}' is not a standard trace field", path))

            case StartEvent():
                pass

            case EndEvent():
                pass

            case MemberOf(elem, set_expr):
                walk(elem, f"{path} > MemberOf.elem", inside_temporal, inside_global)
                walk(set_expr, f"{path} > MemberOf.set", inside_temporal, inside_global)

            case Ancestors(_):
                pass

            case SetLiteral(_):
                pass

            case RawStructural(_, _):
                pass  # structural policies bypass the checker

            case ForAll(_, _, body):
                walk(body, f"{path} > ForAll.body", inside_temporal, inside_global)

            case Exists(_, _, body):
                walk(body, f"{path} > Exists.body", inside_temporal, inside_global)

            case ExistsUnique(_, _, body):
                walk(body, f"{path} > ExistsUnique.body", inside_temporal, inside_global)

            case Equals(left, right):
                walk(left, f"{path} > Equals.left", inside_temporal, inside_global)
                walk(right, f"{path} > Equals.right", inside_temporal, inside_global)

            case _:
                pass

    walk(node, policy_name, False, False)
    return errors, warnings


def check_policy(policy: dict) -> tuple[str, list[CheckError], list[CheckWarning]]:
    """Check one policy for syntax and semantic issues."""
    name = policy['name']
    formula_str = policy.get('formula', '')
    errors: list[CheckError] = []
    warnings: list[CheckWarning] = []

    # Check required fields
    if not policy.get('policy_id'):
        errors.append(CheckError("Missing required field 'policy_id'", name))
    if not policy.get('name'):
        errors.append(CheckError("Missing required field 'name'", name))
    if not policy.get('severity'):
        errors.append(CheckError("Missing required field 'severity'", name))
    elif policy['severity'] not in ('info', 'warning', 'error'):
        errors.append(CheckError(f"Invalid severity '{policy['severity']}' — must be info, warning, or error", name))
    if not policy.get('scope'):
        errors.append(CheckError("Missing required field 'scope'", name))
    elif policy['scope'] not in ('trace', 'action', 'artifact', 'module'):
        errors.append(CheckError(f"Invalid scope '{policy['scope']}' — must be trace, action, artifact, or module", name))
    if not policy.get('kind'):
        errors.append(CheckError("Missing required field 'kind'", name))

    if not formula_str:
        errors.append(CheckError("Missing required field 'formula'", name))
        return name, errors, warnings

    # Structural policies: check formula is present but skip parse
    if name in STRUCTURAL_POLICIES:
        return name, errors, warnings

    # Tokenize
    try:
        tokens = tokenize(formula_str)
    except Exception as e:
        errors.append(CheckError(f"Tokenization failed: {e}", name))
        return name, errors, warnings

    # Check for unrecognized tokens (all should be IDENT, OP, LPAREN, etc.)
    for tok in tokens:
        if tok.kind == 'EOF':
            continue
        if tok.kind == 'IDENT' and tok.value not in (
            VALID_ATOMS | TEMPORAL_OPS | SCOPED_OPS | FIELDS | {'a', 'b', 't', 'action'}
        ):
            # Not necessarily an error — could be a valid identifier we don't know about
            pass

    # Parse
    parser = Parser(tokens, formula_str, name)
    ast = parser.parse()

    if isinstance(ast, RawStructural):
        errors.append(CheckError(f"Parse failed — formula could not be parsed: {formula_str}", name))
        return name, errors, warnings

    # Check that tokens were fully consumed
    if parser.pos < len(parser.tokens) - 1:  # -1 for EOF
        remaining = parser.tokens[parser.pos]
        if remaining.kind != 'EOF':
            warnings.append(CheckWarning(
                f"Unconsumed tokens after position {remaining.pos}: '{remaining.value}...'",
                name
            ))

    # Semantic check
    sem_errors, sem_warnings = check_formula(ast, name)
    errors.extend(sem_errors)
    warnings.extend(sem_warnings)

    return name, errors, warnings


def check_all_policies(policies: list[dict]) -> bool:
    """Check all policies and print results. Returns True if all pass."""
    total_errors = 0
    total_warnings = 0
    all_ok = True

    for p in policies:
        name, errors, warnings = check_policy(p)
        total_errors += len(errors)
        total_warnings += len(warnings)

        if errors:
            all_ok = False
            print(f"\n  FAIL  {name}")
            for e in errors:
                print(f"        error: {e.message}")
                if e.path != name:
                    print(f"               at {e.path}")
        elif warnings:
            print(f"\n  WARN  {name}")
        else:
            print(f"  OK    {name}")

        for w in warnings:
            print(f"        warn:  {w.message}")
            if w.path != name:
                print(f"               at {w.path}")

    print(f"\n{'='*50}")
    print(f"  {len(policies)} policies checked")
    print(f"  {total_errors} errors, {total_warnings} warnings")
    if all_ok and total_warnings == 0:
        print(f"  All policies OK")
    elif all_ok:
        print(f"  All policies parseable ({total_warnings} warnings)")
    else:
        print(f"  {total_errors} policies have errors")
    print()

    return all_ok


# ================================================================
# Full pipeline
# ================================================================

def compile_policy(policy: dict) -> tuple[str, Formula, str]:
    """Parse and compile one policy. Returns (name, ast, iml_code)."""
    name = policy['name']
    formula_str = policy.get('formula', '')

    if not formula_str:
        return name, None, f"(* {name}: no formula defined *)"

    # For structural policies, emit reference to hand-written combinator
    if name in STRUCTURAL_POLICIES:
        ast = RawStructural(formula_str, name)
        iml = gen_iml(ast)
        return name, ast, iml

    tokens = tokenize(formula_str)
    parser = Parser(tokens, formula_str, name)
    ast = parser.parse()
    iml = gen_iml(ast, 'trace')
    return name, ast, iml


def generate_iml_file(policies: list[dict]) -> str:
    """Generate a complete IML file from a list of policies."""
    lines = []
    lines.append('(* ================================================================')
    lines.append('   Generated Policy Definitions')
    lines.append('   ================================================================')
    lines.append('   Auto-generated by policy_compiler.py from trace policy formulas.')
    lines.append('   Depends on policy_combinators.iml for operator definitions.')
    lines.append('   ================================================================ *)')
    lines.append('')
    lines.append('open Policy_combinators')
    lines.append('')

    # Group by classification
    groups = {'pure_temporal': [], 'scoped_temporal': [], 'structural': []}
    for p in policies:
        name, ast, iml = compile_policy(p)
        formula_str = p.get('formula', '')
        classification = classify_formula(name, ast) if ast else 'structural'
        groups[classification].append((name, formula_str, iml, p.get('description', '')))

    for group_name, group_label in [
        ('pure_temporal', 'Pure Temporal Policies'),
        ('scoped_temporal', 'Scoped Temporal Policies'),
        ('structural', 'Structural Policies'),
    ]:
        items = groups[group_name]
        if not items:
            continue

        lines.append(f'(* ---- {group_label} ---- *)')
        lines.append('')

        for name, formula_str, iml, desc in items:
            lines.append(f'(* {desc} *)')
            lines.append(f'(* Formula: {formula_str} *)')
            lines.append(f'let policy_{name} (t : trace) : bool =')
            # Indent the body
            for iml_line in iml.split('\n'):
                lines.append(f'  {iml_line}')
            lines.append('')

    # Aggregate: check all policies
    lines.append('(* ---- Aggregate: all policies ---- *)')
    lines.append('')
    lines.append('let all_policies (t : trace) : bool =')
    for p in policies:
        name = p['name']
        lines.append(f'  policy_{name} t &&')
    # Replace last && with true
    if policies:
        lines[-1] = lines[-1].rstrip(' &&')
    lines.append('')

    return '\n'.join(lines)


# ================================================================
# CLI
# ================================================================

def print_ast(policies: list[dict]):
    """Print parse trees for debugging."""
    for p in policies:
        name = p['name']
        formula_str = p.get('formula', '')
        if not formula_str:
            continue

        print(f"\n{'='*60}")
        print(f"Policy: {name}")
        print(f"Formula: {formula_str}")

        if name in STRUCTURAL_POLICIES:
            print(f"  → structural (hand-written combinator)")
            continue

        tokens = tokenize(formula_str)
        print(f"Tokens: {[(t.kind, t.value) for t in tokens]}")

        parser = Parser(tokens, formula_str, name)
        ast = parser.parse()
        print(f"AST: {ast}")

        classification = classify_formula(name, ast)
        print(f"Classification: {classification}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python policy_compiler.py <trace.json> [--check] [--ast]", file=sys.stderr)
        print("  --check   Validate all policy formulas (syntax + semantics)", file=sys.stderr)
        print("  --ast     Show parse trees for debugging", file=sys.stderr)
        print("  (default) Generate IML source code", file=sys.stderr)
        sys.exit(1)

    trace_file = sys.argv[1]
    show_ast = '--ast' in sys.argv
    do_check = '--check' in sys.argv

    with open(trace_file) as f:
        trace = json.load(f)

    policies = trace.get('policies', [])
    if not policies:
        print("No policies found in trace.", file=sys.stderr)
        sys.exit(1)

    if do_check:
        ok = check_all_policies(policies)
        sys.exit(0 if ok else 1)
    elif show_ast:
        print_ast(policies)
    else:
        print(generate_iml_file(policies))


if __name__ == '__main__':
    main()

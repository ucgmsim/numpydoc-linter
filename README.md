# npdlint

A fast, modular, structurally-aware linter for numpydoc-style docstrings.

It finds its own files, keeps every check as a separate rule, and lets you vary
the rules by the *kind* of thing being documented, so a `@property`, a private
helper and a public function can each be held to a different standard.

```console
$ npdlint check
src/shapes.py:12:5: PT01 Property docstring does not match the type-line form (<type>: <summary>)
src/shapes.py:40:1: PR04 Parameter "radius" has no type
Found 2 issues in 18 files
```

## Why

`numpydoc lint` has the right checks but an awkward shape: it takes a list of
files rather than a project, every check lives inside one function, and the only
way to vary behaviour is a regex over dotted names. That pushes projects into
shell pipelines like `fd . src/ -E __init__.py --extension py | xargs numpydoc lint`.

This tool keeps numpydoc's checks and error codes, and adds:

- **Discovery.** Point it at a directory, or nothing at all. It honours
  `.gitignore`.
- **Rules as objects.** Each check is a class with a code, a name, and the kinds
  of object it applies to. Third-party rules load from entry points or a local file.
- **Scope blocks.** Select and ignore rules by kind, decorator, visibility,
  qualified name, path, and more.
- **Property conventions.** Built-in support for the `type: summary` form that
  numpydoc cannot express.
- **A drop-in migration.** An existing `[tool.numpydoc_validation]` table is
  read as-is, so adopting it changes no configuration on day one.
- **Dataclass awareness.** Fields of a `@dataclass` are the constructor's
  parameters, inherited ones included, so documenting them is not an error.

## Install

```console
pip install npdlint
```

## Usage

```console
npdlint check [PATHS...]      # lint; PATHS defaults to the configured include
npdlint rule PR               # describe rules, by code or prefix
npdlint explain src/x.py:42   # show which rules apply there, and why
```

`check` is the default command, so `npdlint src` works too.

Exit codes are 0 when clean, 1 when violations were found, and 2 when the tool
could not run.

### Output formats

`--output-format` takes `concise` (default), `full`, `json`, `github`, or
`pylint`. Use `github` in CI to get inline annotations on the pull request.
`--statistics` prints counts per rule, which is the quickest way to decide what
to ignore when adopting the tool on an existing codebase.

## Migrating from numpydoc

An existing `[tool.numpydoc_validation]` table is read as-is, so a project
already configured for `numpydoc lint` runs without touching its configuration:

```console
$ npdlint check
```

The table is interpreted with numpydoc's semantics, not this tool's.

| numpydoc setting | Behaviour |
|---|---|
| `checks` | An allow-list, unless it contains `"all"`, in which case it is every numpydoc check minus the ones listed |
| `exclude` | Regular expressions searched against the object's numpydoc name, which is rooted at the file stem rather than the package path |
| `exclude_files` | Regular expressions anchored at the start of the file path |
| `override_<CODE>` | Suppresses one check for an object when the pattern is found in its docstring |

`setup.cfg` with a `[tool:numpydoc_validation]` section works too, and as in
numpydoc it is only consulted when there is no `pyproject.toml`.

`checks = ["all"]` means the 37 checks numpydoc defines and no more, so
adopting this tool never silently turns on rules a project has not asked for.
The `PT` and `DS` rules are opt-in.

Anything written in `[tool.npdlint]` wins over the legacy table, so a
project can migrate one setting at a time. Set `numpydoc-compat = false` to
ignore the legacy table entirely.

The same three features exist natively, under clearer names:

```toml
[tool.npdlint]
exclude-object-patterns = ['\.__repr__$']   # regex on the object name
exclude-file-patterns = ['^generated/']     # regex on the path, anchored

[tool.npdlint.overrides]
SS05 = ['^Process ', '^Access ']            # regex found in the docstring
```

Note that `exclude` in `[tool.npdlint]` is a gitignore-style glob, not
a regular expression. `exclude-file-patterns` is the regex equivalent.

### What is left in the workflow

File selection that used to live in the shell moves into configuration:

```toml
[tool.npdlint]
include = ["mypackage"]
extend-exclude = ["mypackage/vendored.py"]
```

Then the CI step is one line with no project-specific data in it.

## Configuration

Everything lives in `pyproject.toml` under `[tool.npdlint]`. The tool was
called `numpydoc-linter` to begin with, and `[tool.numpydoc-linter]` is still
read when no `[tool.npdlint]` table is present, with a warning on stderr
naming the file. Where both are present the current name wins outright, since
merging the two would make the effective configuration impossible to read off
the file.

```toml
[tool.npdlint]
include = ["src"]
extend-exclude = ["**/tests/**"]
select = ["ALL"]
ignore = ["ES01", "SA01", "EX01"]

[tool.npdlint.per-file-ignores]
"**/__init__.py" = ["GL08"]

# Private helpers are not part of the public API, so they need no docstring.
[[tool.npdlint.scope]]
match = { private = true }
skip = true

# Properties read as attributes, so document them as "type: summary".
[[tool.npdlint.scope]]
match = { kind = "property" }
extend-ignore = ["PR", "RT", "ES01"]
extend-select = ["PT"]
property-form = "type-line"

# Dunder methods only need to exist.
[[tool.npdlint.scope]]
match = { kind = "any-method", dunder = true }
select = ["GL08"]
```

### Excluding files

Directories like `.git`, `.venv`, `build` and `__pycache__` are excluded by
default, and `.gitignore` is honoured. Following ruff, `extend-exclude` adds to
the built-in list while `exclude` replaces it, so reach for `extend-exclude`
unless you really mean to walk everything.

### Selecting rules

Selectors follow ruff. `ALL` matches everything, `PR` matches a family, `PR0` a
partial code, and `PR04` one rule. Where two selectors both match, the more
specific wins; at equal specificity an ignore beats a select.

### Scope blocks

Blocks are evaluated top to bottom. Each matching block layers its overrides on
the result of the previous one, so ordering is explicit rather than a precedence
puzzle. Within a block the order is: `skip`, `select`, `ignore`, `extend-select`,
`extend-ignore`.

A `match` table may combine any of these, and all of them must hold:

| Key | Type | Matches on |
|---|---|---|
| `kind` | string or list | `module`, `class`, `function`, `method`, `property`, `setter`, `classmethod`, `staticmethod`, or the groups `callable`, `any-method`, `any` |
| `name` | regex | the bare name |
| `qualname` | regex | the dotted name from the module root |
| `path` | glob or list | the file, relative to the project root |
| `decorator` | string or list | any decorator, by dotted name |
| `parent-kind` | string or list | the kind of the enclosing object |
| `in-all` | bool | membership of the module's `__all__` |
| `private` | bool | name starts with one underscore |
| `dunder` | bool | name is `__like_this__` |
| `abstract` | bool | decorated `@abstractmethod` |
| `stub` | bool | body is only `pass`, `...`, or `raise NotImplementedError` |
| `overload` | bool | decorated `@overload` |
| `override` | bool | decorated `@override` |
| `async` | bool | declared `async def` |
| `generator` | bool | contains a `yield` |
| `returns-value` | bool | contains a `return <expr>` |
| `has-docstring` | bool | has a docstring at all |
| `dataclass` | bool | a decorator synthesises the constructor |
| `nested` | bool | defined inside a function body |

Run `npdlint explain path.py:42` when a rule fires and you expected it not to.
It prints the target's flags and every layer of the resolution.

### Property forms

`property-form` selects what a `@property` docstring should look like.

| Form | Shape |
|---|---|
| `returns-section` | plain numpydoc, with a Returns section; the default |
| `type-line` | `float: The radius in metres.` |
| `summary-only` | a summary with no type |
| `{ regex = "..." }` | your own, with optional `type` and `summary` groups |

`PT02` compares a captured `type` group against the return annotation, so
`int: ...` on a method annotated `-> str` is reported.

### Dataclasses

A `@dataclass` has no `__init__` in the syntax tree, so numpydoc sees an empty
signature and calls every documented field an unknown parameter. This linter
derives the constructor the decorator will synthesise: annotated attributes in
order, `ClassVar` and `field(init=False)` excluded, `InitVar` unwrapped, and
fields inherited from a base class in the same file merged in first. Where a
base class lives in another module its fields cannot be seen, so documented
names that are not accounted for are left alone rather than reported.

A field is a constructor parameter and an attribute at the same time, and real
code documents it in any of three places. All three count: the `Parameters`
section, the `Attributes` section, and an inline attribute docstring, which is
a bare string literal directly below the field.

```python
@dataclass
class Point:
    """
    A point.

    Attributes
    ----------
    x : int
        The x.
    """

    x: int
    y: int
    """The y."""
```

Set `dataclass-fields-section = "parameters"` to accept only the `Parameters`
section, as numpydoc would. Names documented under `Attributes` are not treated
as declared parameters, so a property or `ClassVar` described there is not
reported as an unknown parameter and has no position to be out of order.

`attrs` and pydantic dataclasses are recognised too; add more with
`dataclass-decorators`.

### Stub files

`.pyi` files are not linted by default: a stub carries the signatures while the
implementation carries the docstrings. Set `include-stubs = true` to lint them.

### Private parameters

By default every parameter needs documenting, as numpydoc requires. Set
`private-parameters = "ignore"` to exempt underscore-prefixed ones, which is
useful for dataclasses that carry private caches. The exemption is symmetric:
an exempt parameter is neither required nor rejected.

### Suppressing inline

`# noqa: PR04,RT01` suppresses those rules for the object it sits on, and a bare
`# noqa` suppresses everything. numpydoc's `# numpydoc ignore=PR04` spelling is
accepted too, so existing suppressions keep working.

The comment may go anywhere in the signature, which matters because the natural
place for it is rarely the `def` line:

```python
@overload
def f(
    x: int,
) -> int:  # numpydoc ignore=GL08
    ...
```

The docstring's closing line works as well. A comment inside the body does not
count, which is where this differs from numpydoc: numpydoc attaches a
suppression to the most recent `def` it has seen, so a comment buried deep in a
function body silently suppresses that function's checks.

### Suppressions that suppress nothing

A suppression outlives the problem it was written for. The docstring gets its
`Returns` section, nobody deletes the `# numpydoc ignore=RT01` above it, and
from then on the comment is both useless and misleading: the next reader takes
it as evidence that the rule still fires there, and it hides the rule if the
docstring later regresses.

`NQ01` reports a comment that did no work, and `NQ02` one that names a rule
code no rule answers to:

```
src/geometry.py:41:23: NQ01 Unnecessary suppression comment: RT01 was not reported for this object
src/geometry.py:88:19: NQ01 Unnecessary suppression comment: it applies to no documented object
src/geometry.py:96:19: NQ02 Suppression comment names unknown rule code RT09
```

Both are on by default, and both are ordinary rules: `ignore = ["NQ"]` in
`[tool.npdlint]`, a `per-file-ignores` entry, or `--ignore NQ` on the
command line turns them off. They are the only rules that judge the file
rather than an object in it, so scope blocks do not apply to them.

What counts as unnecessary is deliberately conservative, because the cost of a
false positive is a user deleting a comment they needed:

- **A rule your configuration already disabled is never judged.** Running with
  a narrowed `--select`, a `skip`ping scope block, `exclude-object-patterns`,
  or an `overrides` pattern leaves the comments for those rules alone, so a
  partial run cannot condemn them.
- **`# noqa` is shared with other linters, so only codes registered here are
  judged in one.** `# noqa: F401` is ruff's business, and a bare `# noqa` is
  left alone entirely. `# numpydoc ignore` is addressed to this tool alone, so
  everything in one is judged, a bare `# numpydoc ignore` included.
- **Only the unused codes are named.** `# numpydoc ignore=GL08,RT01` on an
  undocumented function reports `RT01` and says nothing about `GL08`.
- **A comment can exempt itself**, by naming the rule: `# numpydoc
  ignore=RT01,NQ01` keeps a suppression you want to hold on to.

A comment that applies to no documented object is reported too. That is the
other half of the divergence above: numpydoc would attach a suppression
written in a function body to the function, and this linter does not, so
`NQ01` names the comments that stopped working when you migrated rather than
letting them fail quietly.

## Continuous integration

Replacing a `fd | xargs numpydoc lint` pipeline:

```yaml
- uses: actions/setup-python@v5
- run: pip install npdlint
- run: npdlint check --output-format github
```

What used to be workflow inputs, such as the package directory, extra
excludes, and the `__init__.py` exemption, move into `pyproject.toml`, so the
workflow step carries no project-specific data.

Or as a pre-commit hook:

```yaml
repos:
  - repo: https://github.com/ucgmsim/numpydoc-linter
    rev: v0.1.0
    hooks:
      - id: npdlint
```

## Rules

Codes `GL`, `SS`, `ES`, `PR`, `RT`, `YD`, `SA` and `EX` are ports of numpydoc's
checks and keep its codes and wording, so existing ignore lists carry over
unchanged. `PT` covers property forms, `DS01` reports a docstring the parser
cannot read, and `NQ` reports suppression comments that are not doing anything.
Run `npdlint rule` for the full list.

### Differences from numpydoc

A differential test lints a shared corpus with both tools and requires them to
agree, so every difference below is deliberate and pinned down by a test.

1. **`GL08` on `__init__`.** numpydoc documents that a properly formatted class
   docstring silences this for an undocumented constructor. Its AST hook gets
   this wrong in both directions, reporting it when the class does document the
   parameters and skipping it when the class has no docstring at all. This
   linter implements the documented behaviour.
2. **`PR01` and `PR02` on dataclasses.** See above. numpydoc's own test suite
   contains a dataclass annotated "As param1 is not documented this class should
   also raise PR01", which numpydoc does not raise and this linter does.
3. **`YD01` on `yield from`.** numpydoc's generator check looks only for a bare
   `yield` statement among a function's direct children, so it misses
   `yield from` and any yield inside a branch or loop.
4. **Nested objects.** numpydoc's visitor stops at anything that is not a
   module, class or function, so a function defined inside an `if` or a `for` is
   never checked while one defined directly in a body is. This linter is
   consistent. To keep numpydoc's effective behaviour, skip them:

   ```toml
   [[tool.npdlint.scope]]
   match = { nested = true }
   skip = true
   ```
5. **Malformed docstrings.** A docstring that breaks the parser makes numpydoc
   abandon the whole file. This linter reports `DS01` and carries on.
6. **Suppression syntax.** A bare `# noqa` or `# numpydoc ignore`, with no
   codes, suppresses everything on its line here; numpydoc recognises only
   `# numpydoc ignore=CODE`. The `NQ` rules above have no numpydoc equivalent,
   and a `[tool.numpydoc_validation]` table never enables them.

### Performance

On 1076 files of third-party Python, with every rule enabled:

| Tool | Wall clock |
|---|---|
| `numpydoc lint`, 1 process | 30.1 s |
| `npdlint`, 1 process | 7.5 s |
| `npdlint`, 8 processes | 3.0 s |

numpydoc also failed to parse 4 of those files.

## Writing your own rules

Point at a local file, or ship a package that advertises the
`npdlint.rules` entry point.

```toml
[tool.npdlint]
plugins = ["tools/doc_rules.py"]
```

```python
from npdlint.rules import BaseRule, registry
from npdlint.targets import Kind


@registry.register
class SummaryMentionsUnits(BaseRule):
    code = "X001"
    name = "summary-mentions-units"
    summary = "Physical quantities should state their units."
    kinds = frozenset({Kind.PROPERTY})

    def check(self, target, ctx):
        doc = target.docstring
        if "metres" not in doc.summary and target.name.endswith("_m"):
            yield self.diagnostic(target, "summary should state the units")
```

Subclass `BaseFileRule` instead for a check on the file as a whole. It runs
once, after every object has been checked, and implements `check_file(ctx)`
rather than `check`; `ctx.source` is the parsed file and `self.at(ctx, line,
col, message)` builds the diagnostic. The `NQ` rules are written this way.

## Licence

BSD 3-Clause. `src/npdlint/_vendor/docscrape.py` is vendored from
numpydoc under the same licence; its copyright notice is kept alongside it.

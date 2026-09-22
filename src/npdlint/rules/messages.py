"""Message templates.

Codes GL, SS, ES, PR, RT, YD, SA and EX keep numpydoc's wording verbatim so
that migrating from ``numpydoc lint`` needs no change to existing ignore lists.
"""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    # -- docstring integrity ----------------------------------------------
    "DS01": "Docstring could not be parsed: {reason}",
    # -- general ---------------------------------------------------------
    "GL01": (
        "Docstring text (summary) should start right after, or on the line "
        "following the opening quotes"
    ),
    "GL02": (
        "Closing quotes should be placed in the line after the last text in "
        "the docstring (do not close the quotes in the same line as the text, "
        "or leave a blank line between the last text and the quotes)"
    ),
    "GL03": (
        "Double line break found; please use only one blank line to separate "
        "sections or paragraphs, and do not leave blank lines at the end of "
        "docstrings"
    ),
    "GL05": (
        'Tabs found at the start of line "{line_with_tabs}", please use '
        "whitespace only"
    ),
    "GL06": (
        'Found unknown section "{section}". Allowed sections are: '
        "{allowed_sections}"
    ),
    "GL07": "Sections are in the wrong order. Correct order is: {correct_sections}",
    "GL08": "The object does not have a docstring",
    "GL09": "Deprecation warning should precede extended summary",
    "GL10": "reST directives {directives} must be followed by two colons",
    # -- short summary ---------------------------------------------------
    "SS01": (
        "No summary found (a short summary in a single line should be present "
        "at the beginning of the docstring)"
    ),
    "SS02": "Summary does not start with a capital letter",
    "SS03": "Summary does not end with a period",
    "SS04": "Summary contains heading whitespaces",
    "SS05": (
        "Summary must start with infinitive verb, not third person "
        '(e.g. use "Generate" instead of "Generates")'
    ),
    "SS06": "Summary should fit in a single line",
    # -- extended summary ------------------------------------------------
    "ES01": "No extended summary found",
    # -- parameters ------------------------------------------------------
    "PR01": "Parameters {missing_params} not documented",
    "PR02": "Unknown parameters {unknown_params}",
    "PR03": (
        "Wrong parameters order. Actual: {actual_params}. "
        "Documented: {documented_params}"
    ),
    "PR04": 'Parameter "{param_name}" has no type',
    "PR05": 'Parameter "{param_name}" type should not finish with "."',
    "PR06": (
        'Parameter "{param_name}" type should use "{right_type}" instead of '
        '"{wrong_type}"'
    ),
    "PR07": 'Parameter "{param_name}" has no description',
    "PR08": 'Parameter "{param_name}" description should start with a capital letter',
    "PR09": 'Parameter "{param_name}" description should finish with "."',
    "PR10": (
        'Parameter "{param_name}" requires a space before the colon separating '
        "the parameter name and type"
    ),
    # -- returns and yields ----------------------------------------------
    "RT01": "No Returns section found",
    "RT02": (
        "The first line of the Returns section should contain only the type, "
        "unless multiple values are being returned"
    ),
    "RT03": "Return value has no description",
    "RT04": "Return value description should start with a capital letter",
    "RT05": 'Return value description should finish with "."',
    "YD01": "No Yields section found",
    # -- see also and examples -------------------------------------------
    "SA01": "See Also section not found",
    "SA02": (
        'Missing period at end of description for See Also "{reference_name}" '
        "reference"
    ),
    "SA03": (
        'Description should be capitalized for See Also "{reference_name}" '
        "reference"
    ),
    "SA04": 'Missing description for See Also "{reference_name}" reference',
    "EX01": "No examples section found",
    # -- properties (new in npdlint) ------------------------------
    "PT01": "Property docstring does not match the {form} form ({expected})",
    "PT02": (
        'Property documents type "{documented}" but is annotated "{annotated}"'
    ),
    "PT03": (
        'Property docstring has a "{section}" section, which the {form} form '
        "does not use"
    ),
    # -- suppression comments (new in npdlint) --------------------
    "NQ01": "Unnecessary suppression comment: {detail}",
    "NQ02": "Suppression comment names {detail}",
}


def render(code: str, **kwargs: object) -> str:
    """
    Render a message template.

    Parameters
    ----------
    code : str
        The rule code.
    **kwargs : object
        Values interpolated into the template.

    Returns
    -------
    str
        The rendered message.
    """
    return MESSAGES[code].format(**kwargs)

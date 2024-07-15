SHELL_HISTORY = """
Please provide a summary of the given shell history log. The summary should cover all the key points and main ideas presented in the original text, while also condensing the information into a concise and easy-to-understand format. Please ensure that the summary includes relevant details and examples that support the main ideas, while avoiding any unnecessary information or repetition. The length of the summary should be appropriate for the length and complexity of the original text, providing a clear and accurate overview without omitting any important information.
<shell history>
{file_content}
</shell history>
Please provide a summary of the given shell history log. The summary should cover all the key points and main ideas presented in the original text, while also condensing the information into a concise and easy-to-understand format. Please ensure that the summary includes relevant details and examples that support the main ideas, while avoiding any unnecessary information or repetition. The length of the summary should be appropriate for the length and complexity of the original text, providing a clear and accurate overview without omitting any important information.
"""

SHELL_HISTORY_SUMMARY = """
Please provide a summary of the given summary of a shell history log. The summary should cover all the key points and main ideas presented in the original text, while also condensing the information into a concise and easy-to-understand format. Please ensure that the summary includes relevant details and examples that support the main ideas, while avoiding any unnecessary information or repetition. The length of the summary should be appropriate for the length and complexity of the original text, providing a clear and accurate overview without omitting any important information.
"""

registry = {
    "shell:bash:history": {
        "triage": SHELL_HISTORY,
        "summary": SHELL_HISTORY_SUMMARY,
    },
    "shell:zsh:history": {
        "triage": SHELL_HISTORY,
        "summary": SHELL_HISTORY_SUMMARY,
    },
    "shell:powershell:history": {
        "triage": SHELL_HISTORY,
        "summary": SHELL_HISTORY_SUMMARY,
    },
    "file:generic": {
        "triage": SHELL_HISTORY,
        "summary": SHELL_HISTORY_SUMMARY,
    },
}

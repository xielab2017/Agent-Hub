from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"


def test_folder_toggle_displays_tasks_in_main_view():
    source = APP_JS.read_text(encoding="utf-8")
    handler_start = source.index('header.querySelector("[data-folder-toggle]").onclick')
    handler_end = source.index("};", handler_start)
    handler = source[handler_start:handler_end]

    assert "renderFolderOverview(folderId)" in handler


def test_folder_task_requires_double_click_to_open_chat():
    source = APP_JS.read_text(encoding="utf-8")
    function_start = source.index("function renderFolderOverview(folderId)")
    function_end = source.index("\nasync function loadAgents", function_start)
    function_body = source[function_start:function_end]

    assert "row.onclick = () =>" in function_body
    assert "row.ondblclick = () => selectSession(s.id)" in function_body
    assert 'event.key !== "Enter"' in function_body


def test_selecting_current_session_restores_conversation_surface():
    source = APP_JS.read_text(encoding="utf-8")
    function_start = source.index("async function selectSession(id)")
    function_end = source.index("\nfunction renderMessages", function_start)
    function_body = source[function_start:function_end]

    assert 'prevId === id' not in function_body
    assert '"#control-overlay", "#fs-overlay", "#wf-overlay"' in function_body
    assert "setSidebarOpen(false)" in function_body
    assert "renderMessages(s.messages || [])" in function_body

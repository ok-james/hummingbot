from os.path import dirname, join, realpath
from typing import Dict

from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer
from prompt_toolkit.layout import Dimension
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    VSplit,
    Window,
    WindowAlign,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.widgets import Box, Button, SearchToolbar

from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.client.settings import MAXIMUM_LOG_PANE_LINE_COUNT, MAXIMUM_OUTPUT_PANE_LINE_COUNT
from hummingbot.client.tab.data_types import CommandTab
from hummingbot.client.ui.custom_widgets import CustomTextArea as TextArea, FormattedTextLexer

HEADER = """
                                                *,.
                                                *,,,*
                                            ,,,,,,,               *
                                            ,,,,,,,,            ,,,,
                                            *,,,,,,,,(        .,,,,,,
                                        /,,,,,,,,,,     .*,,,,,,,,
                                        .,,,,,,,,,,,.  ,,,,,,,,,,,*
                                        ,,,,,,,,,,,,,,,,,,,,,,,,,,,
                            //      ,,,,,,,,,,,,,,,,,,,,,,,,,,,,#*%
                        .,,,,,,,,. *,,,,,,,,,,,,,,,,,,,,,,,,,,,%%%%%%&@
                        ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,%%%%%%%&
                    ,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,%%%%%%%&
                    /*,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,(((((%%&
                **.         #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,((((((((((#.
            **               *,,,,,,,,,,,,,,,,,,,,,,,,**/(((((((((((((*
                                ,,,,,,,,,,,,,,,,,,,,*********((((((((((((
                                ,,,,,,,,,,,,,,,**************((((((((@
                                (,,,,,,,,,,,,,,,***************(#
                                    *,,,,,,,,,,,,,,,,**************/
                                    ,,,,,,,,,,,,,,,***************/
                                        ,,,,,,,,,,,,,,****************
                                        .,,,,,,,,,,,,**************/
                                            ,,,,,,,,*******,
                                            *,,,,,,,,********
                                            ,,,,,,,,,/******/
                                            ,,,,,,,,,@  /****/
                                            ,,,,,,,,
                                            , */


██   ██ ██    ██ ███    ███ ███    ███ ██ ███    ██  ██████  ██████   ██████  ████████
██   ██ ██    ██ ████  ████ ████  ████ ██ ████   ██ ██       ██   ██ ██    ██    ██
███████ ██    ██ ██ ████ ██ ██ ████ ██ ██ ██ ██  ██ ██   ███ ██████  ██    ██    ██
██   ██ ██    ██ ██  ██  ██ ██  ██  ██ ██ ██  ██ ██ ██    ██ ██   ██ ██    ██    ██
██   ██  ██████  ██      ██ ██      ██ ██ ██   ████  ██████  ██████   ██████     ██

=======================================================================================
Welcome to Hummingbot, an open source software client that helps you build and run
high-frequency trading (HFT) bots.

Helpful Links:
- Get 24/7 support: https://discord.hummingbot.io
- Learn how to use Hummingbot: https://docs.hummingbot.io
- Earn liquidity rewards: https://miner.hummingbot.io

Useful Commands:
- connect     List available exchanges and add API keys to them
- create      Create a new bot
- import      Import an existing bot by loading the configuration file
- help        List available commands

"""

with open(realpath(join(dirname(__file__), "../../VERSION"))) as version_file:
    version = version_file.read().strip()


def create_input_field(lexer=None, completer: Completer = None):
    return TextArea(
        height=10,
        prompt=">>> ",
        style="class:input_field",
        multiline=False,
        focus_on_click=True,
        lexer=lexer,
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        complete_while_typing=True,
    )


def create_output_field(client_config_map: ClientConfigAdapter):
    return TextArea(
        style="class:output_field",
        focus_on_click=False,
        read_only=False,
        scrollbar=True,
        max_line_count=MAXIMUM_OUTPUT_PANE_LINE_COUNT,
        initial_text=HEADER,
        lexer=FormattedTextLexer(client_config_map),
    )


def create_timer():
    return TextArea(
        style="class:footer",
        focus_on_click=False,
        read_only=False,
        scrollbar=False,
        max_line_count=1,
        width=30,
    )


def create_process_monitor():
    return TextArea(
        style="class:footer",
        focus_on_click=False,
        read_only=False,
        scrollbar=False,
        max_line_count=1,
        align=WindowAlign.RIGHT,
    )


def create_trade_monitor():
    return TextArea(
        style="class:footer",
        focus_on_click=False,
        read_only=False,
        scrollbar=False,
        max_line_count=1,
    )


def create_search_field() -> SearchToolbar:
    return SearchToolbar(
        text_if_not_searching=[("class:primary", "[CTRL + F] to start searching.")],
        forward_search_prompt=[("class:primary", "Search logs [Press CTRL + F to hide search] >>> ")],
        ignore_case=True,
    )


def create_log_field(search_field: SearchToolbar):
    return TextArea(
        style="class:log_field",
        text="Running Logs\n",
        focus_on_click=False,
        read_only=False,
        scrollbar=True,
        max_line_count=MAXIMUM_LOG_PANE_LINE_COUNT,
        initial_text="Running Logs \n",
        search_field=search_field,
        preview_search=False,
    )


def create_live_field():
    return TextArea(
        style="class:log_field",
        focus_on_click=False,
        read_only=False,
        scrollbar=True,
        max_line_count=MAXIMUM_OUTPUT_PANE_LINE_COUNT,
    )


def create_log_toggle(function):
    return Button(
        text="> log pane",
        width=13,
        handler=function,
        left_symbol="",
        right_symbol="",
    )


def create_tab_button(text, function, margin=2, left_symbol=" ", right_symbol=" "):
    return Button(
        text=text, width=len(text) + margin, handler=function, left_symbol=left_symbol, right_symbol=right_symbol
    )


def get_version():
    return [("class:header", f"Version: {version}")]


def get_active_strategy():
    from hummingbot.client.hummingbot_application import HummingbotApplication

    hb = HummingbotApplication.main_application()
    style = "class:log_field"
    return [(style, f"Strategy: {hb.strategy_name}")]


def get_strategy_file():
    from hummingbot.client.hummingbot_application import HummingbotApplication

    hb = HummingbotApplication.main_application()
    style = "class:log_field"
    return [(style, f"Strategy File: {hb._strategy_file_name}")]


def get_gateway_status():
    from hummingbot.client.hummingbot_application import HummingbotApplication

    hb = HummingbotApplication.main_application()
    gateway_status = hb._gateway_monitor.gateway_status.name
    style = "class:log_field"
    return [(style, f"Gateway: {gateway_status}")]


def generate_layout(
    input_field: TextArea,
    output_field: TextArea,
    log_field: TextArea,
    right_pane_toggle: Button,
    log_field_button: Button,
    # 通过 ctrl + f 展示的搜索功能
    search_field: SearchToolbar,
    timer: TextArea,
    process_monitor: TextArea,
    trade_monitor: TextArea,
    command_tabs: Dict[str, CommandTab],
):
    components = {}

    # FormattedTextControl 用于显示格式化文本的控制器。这个控制器可以用于创建用户界面（User Interface，UI）中的文本区域，其中文本可以具有不同的样式、颜色和格式。
    components["item_top_version"] = Window(FormattedTextControl(get_version), style="class:header")
    components["item_top_active"] = Window(FormattedTextControl(get_active_strategy), style="class:header")
    components["item_top_file"] = Window(FormattedTextControl(get_strategy_file), style="class:header")
    components["item_top_gateway"] = Window(FormattedTextControl(get_gateway_status), style="class:header")
    # 上方展开和隐藏 log pane 的文本（> log pane）
    components["item_top_toggle"] = right_pane_toggle
    # VSplit（垂直分割）：是一个容器，用于将其子组件垂直分割成多个部分，每个部分可以包含不同的子组件。
    # height 参数是用于设置子组件的高度的。它指定了子组件在垂直方向上所占用的高度比例，假设 Vsplit 容器的高度是 100 像素，则设置 height 为 0.5 ，那么子组件的高度就是 50 像素
    # pane_top 是 Top navigation bar
    components["pane_top"] = VSplit(
        [
            components["item_top_version"],
            components["item_top_active"],
            components["item_top_file"],
            components["item_top_gateway"],
            components["item_top_toggle"],
        ],
        height=1,
    )
    # pane_bottom 是 Bottom navigation bar
    components["pane_bottom"] = VSplit([trade_monitor, process_monitor, timer], height=1)
    # 左上方的 Output pane，其中 padding 的单位是字符宽度，比如 padding_left = 2 就是指左侧两字符的边距宽度
    output_pane = Box(body=output_field, padding=0, padding_left=2, style="class:output_field")
    # 左下方的 Input pane
    input_pane = Box(body=input_field, padding=0, padding_left=2, padding_top=1, style="class:input_field")
    # 左侧的布局，在 input_pane 创建实例时，传入了 height=10 ，所以高度固定，output_pane 占据剩余的空间
    components["pane_left"] = HSplit([output_pane, input_pane], width=Dimension(weight=1))

    # all(...) 函数用于检查生成器表达式中的所有布尔值是否都为 True
    # 所以整个语句的作用是判断 command_tabs 中所有项的 is_selected 都为 False
    if all(not t.is_selected for t in command_tabs.values()):
        # 如果所有都为 False ，则将当前 Tab 设置为选中
        log_field_button.window.style = "class:tab_button.focused"
    else:
        log_field_button.window.style = "class:tab_button"
    # Tabs 的按钮，按钮的选中状态要与下方的内容匹配上
    tab_buttons = [log_field_button]
    for tab in sorted(command_tabs.values(), key=lambda x: x.tab_index):
        if tab.button is not None:
            if tab.is_selected:
                tab.button.window.style = "class:tab_button.focused"
            else:
                tab.button.window.style = "class:tab_button"
            tab.close_button.window.style = tab.button.window.style
            tab_buttons.append(VSplit([tab.button, tab.close_button]))
    # 当前在 Tabs 下方要展示的内容，要与选中的 Tab 按钮匹配上
    pane_right_field = log_field
    # 如果存在其他的页签，并且处于选中状态，则选中对应的页签
    focused_right_field = [tab.output_field for tab in command_tabs.values() if tab.is_selected]
    if focused_right_field:
        pane_right_field = focused_right_field[0]

    # 右上方的 Log pane 的 Tabs
    components["pane_right_top"] = VSplit(tab_buttons, height=1, style="class:log_field", padding_char=" ", padding=2)
    # ConditionalContainer 作用是根据条件来选择性地包含或排除其他控件。它允许您根据条件动态地切换控件的可见性，
    # 通过 filter 来控制显示和隐藏， True 表示显示， False 表示隐藏
    components["pane_right"] = ConditionalContainer(
        Box(
            body=HSplit([components["pane_right_top"], pane_right_field, search_field], width=Dimension(weight=1)),
            padding=0,
            padding_left=2,
            style="class:log_field",
        ),
        filter=True,
    )
    # 创建了一个提示菜单（hint menu），用于显示自动补全或建议的选项列表，以帮助用户输入或选择内容。
    components["hint_menus"] = [
        Float(xcursor=True, ycursor=True, transparent=True, content=CompletionsMenu(max_height=16, scroll_offset=1))
    ]

    # 页面的完整布局
    root_container = HSplit(
        [
            components["pane_top"],
            # FloatContainer 浮动容器的作用是在用户界面中以浮动的方式显示内容，通常用于实现一些弹出式的小窗口或下拉菜单
            # 其中包含了左侧部分 (components["pane_left"]) 和提示菜单 (components["hint_menus"])。这意味着左侧部分和提示菜单将位于同一位置，并且提示菜单可以浮动在文本内容之上，通常用于显示自动补全或建议的选项。
            VSplit([FloatContainer(components["pane_left"], components["hint_menus"]), components["pane_right"]]),
            components["pane_bottom"],
        ]
    )
    return Layout(root_container, focused_element=input_field), components

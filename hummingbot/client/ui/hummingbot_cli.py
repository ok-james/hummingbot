import asyncio
import logging
import threading
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Union

from prompt_toolkit.application import Application
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from prompt_toolkit.completion import Completer
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.processors import BeforeInput, PasswordProcessor

from hummingbot import init_logging
from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.client.tab.data_types import CommandTab
from hummingbot.client.ui.interface_utils import start_process_monitor, start_timer, start_trade_monitor
from hummingbot.client.ui.layout import (
    create_input_field,
    create_live_field,
    create_log_field,
    create_log_toggle,
    create_output_field,
    create_process_monitor,
    create_search_field,
    create_tab_button,
    create_timer,
    create_trade_monitor,
    generate_layout,
)
from hummingbot.client.ui.stdout_redirection import patch_stdout
from hummingbot.client.ui.style import load_style
from hummingbot.core.event.events import HummingbotUIEvent
from hummingbot.core.pubsub import PubSub
from hummingbot.core.utils.async_utils import safe_ensure_future

if TYPE_CHECKING:
    from hummingbot.client.hummingbot_application import HummingbotApplication


# Monkey patching here as _handle_exception gets the UI hanged into Press ENTER screen mode
def _handle_exception_patch(self, loop, context):
    if "exception" in context:
        logging.getLogger(__name__).error(
            f"Unhandled error in prompt_toolkit: {context.get('exception')}", exc_info=True
        )


Application._handle_exception = _handle_exception_patch


# 主要用来管理 UI 的渲染、用户输入命令的处理以及交易的监控，监控交易也是为了渲染交易的信息
class HummingbotCLI(PubSub):
    def __init__(
        self,
        client_config_map: ClientConfigAdapter,
        input_handler: Callable,
        bindings: KeyBindings,
        completer: Completer,
        command_tabs: Dict[str, CommandTab],
    ):
        super().__init__()
        self.client_config_map: Union[ClientConfigAdapter, ClientConfigMap] = client_config_map
        self.command_tabs = command_tabs
        # 点击 ctrl + f 时展示的搜索功能
        self.search_field = create_search_field()
        # 左下方的 Input pane
        self.input_field = create_input_field(completer=completer)
        # 左上方的 Output pane
        self.output_field = create_output_field(client_config_map)
        # 右侧的 Log pane
        self.log_field = create_log_field(self.search_field)
        # 上方展开和收起 log pane 的文本
        self.right_pane_toggle = create_log_toggle(self.toggle_right_pane)
        # 从代码来看，暂时没有用到
        self.live_field = create_live_field()
        # 右侧 Log pane 这个创建的 Tab 名字，如果有多个 Tab 存在的话，可以通过点击这个来切换
        self.log_field_button = create_tab_button("Log-pane", self.log_button_clicked)
        # Bottom navigation bar 右侧的运行时间，Uptime
        self.timer = create_timer()
        # Bottom navigation bar 右侧的进程监控，比如 CPU 、 Mem 等
        self.process_usage = create_process_monitor()
        # Bottom navigation bar 左侧的交易监控
        self.trade_monitor = create_trade_monitor()
        # layout 是页面渲染的实例
        # layout_components 是页面渲染的所有区域的字典对象
        self.layout, self.layout_components = generate_layout(
            self.input_field,
            self.output_field,
            self.log_field,
            self.right_pane_toggle,
            self.log_field_button,
            self.search_field,
            self.timer,
            self.process_usage,
            self.trade_monitor,
            self.command_tabs,
        )
        # add self.to_stop_config to know if cancel is triggered
        self.to_stop_config: bool = False

        self.live_updates = False
        self.bindings = bindings
        self.input_handler = input_handler
        self.input_field.accept_handler = self.accept
        self.app: Optional[Application] = None

        # settings
        self.prompt_text = ">>> "
        self.pending_input = None
        self.input_event = None
        self.hide_input = False

        # stdout redirection stack
        # _stdout_redirect_context 的作用是用于重定向标准输出（stdout）以捕获和显示应用程序的日志信息。
        # ExitStack 是一个上下文管理器
        self._stdout_redirect_context: ExitStack = ExitStack()

        # start ui tasks
        # 异步调用
        loop = asyncio.get_event_loop()
        # 开始运行时间的倒计时
        loop.create_task(start_timer(self.timer))
        # 开始监控进程的状态
        loop.create_task(start_process_monitor(self.process_usage))
        # 开始交易监控，将最新的交易信息打印到 trade_monitor 中，包括交易数量、总盈亏和平均收益率。
        loop.create_task(start_trade_monitor(self.trade_monitor))

    def did_start_ui(self):
        # 通过 enter_context 方法，将一个名为 patch_stdout 的上下文管理器（这个上下文管理器的作用是重定向 stdout）添加到 _stdout_redirect_context 中，使其生效。
        # 这样，所有写入 stdout 的内容都会被重定向到日志输出区域 log_field 中。
        self._stdout_redirect_context.enter_context(patch_stdout(log_field=self.log_field))

        log_level = self.client_config_map.log_level
        init_logging("hummingbot_logs.yml", self.client_config_map, override_log_level=log_level)

        self.trigger_event(HummingbotUIEvent.Start, self)

    async def run(self):
        self.app = Application(
            layout=self.layout,
            full_screen=True,
            key_bindings=self.bindings,
            style=load_style(self.client_config_map),
            mouse_support=True,
            clipboard=PyperclipClipboard(),
        )
        # pre_run 参数用于设置在异步事件循环运行之前要执行的函数。这个函数将在异步事件循环启动之前被调用，通常用于执行一些初始化或预处理工作。
        await self.app.run_async(pre_run=self.did_start_ui)
        # self._stdout_redirect_context.close() 不会等待用户界面运行结束，但它可能会等待在 self.did_start_ui() 中启动的任务完成后才继续执行。
        self._stdout_redirect_context.close()

    def accept(self, buff):
        self.pending_input = self.input_field.text.strip()

        if self.input_event:
            self.input_event.set()

        try:
            if self.hide_input:
                output = ""
            else:
                output = "\n>>>  {}".format(
                    self.input_field.text,
                )
                self.input_field.buffer.append_to_history()
        except BaseException as e:
            output = str(e)

        self.log(output)
        self.input_handler(self.input_field.text)

    def clear_input(self):
        self.pending_input = None

    def log(self, text: str, save_log: bool = True):
        if save_log:
            if self.live_updates:
                self.output_field.log(text, silent=True)
            else:
                self.output_field.log(text)
        else:
            self.output_field.log(text, save_log=False)

    def change_prompt(self, prompt: str, is_password: bool = False):
        self.prompt_text = prompt
        processors = []
        if is_password:
            processors.append(PasswordProcessor())
        processors.append(BeforeInput(prompt))
        self.input_field.control.input_processors = processors

    async def prompt(self, prompt: str, is_password: bool = False) -> str:
        self.change_prompt(prompt, is_password)
        self.app.invalidate()
        self.input_event = asyncio.Event()
        await self.input_event.wait()

        temp = self.pending_input
        self.clear_input()
        self.input_event = None

        if is_password:
            masked_string = "*" * len(temp)
            self.log(f"{prompt}{masked_string}")
        else:
            self.log(f"{prompt}{temp}")
        return temp

    def set_text(self, new_text: str):
        self.input_field.document = Document(text=new_text, cursor_position=len(new_text))

    def toggle_hide_input(self):
        self.hide_input = not self.hide_input

    def toggle_right_pane(self):
        if self.layout_components["pane_right"].filter():
            self.layout_components["pane_right"].filter = lambda: False
            self.layout_components["item_top_toggle"].text = "< log pane"
        else:
            self.layout_components["pane_right"].filter = lambda: True
            self.layout_components["item_top_toggle"].text = "> log pane"

    def log_button_clicked(self):
        for tab in self.command_tabs.values():
            tab.is_selected = False
        self.redraw_app()

    def tab_button_clicked(self, command_name: str):
        for tab in self.command_tabs.values():
            tab.is_selected = False
        self.command_tabs[command_name].is_selected = True
        self.redraw_app()

    def exit(self):
        self.app.exit()

    def redraw_app(self):
        self.layout, self.layout_components = generate_layout(
            self.input_field,
            self.output_field,
            self.log_field,
            self.right_pane_toggle,
            self.log_field_button,
            self.search_field,
            self.timer,
            self.process_usage,
            self.trade_monitor,
            self.command_tabs,
        )
        self.app.layout = self.layout
        self.app.invalidate()

    def tab_navigate_left(self):
        selected_tabs = [t for t in self.command_tabs.values() if t.is_selected]
        if not selected_tabs:
            return
        selected_tab: CommandTab = selected_tabs[0]
        if selected_tab.tab_index == 1:
            self.log_button_clicked()
        else:
            left_tab = [t for t in self.command_tabs.values() if t.tab_index == selected_tab.tab_index - 1][0]
            self.tab_button_clicked(left_tab.name)

    def tab_navigate_right(self):
        current_tabs = [t for t in self.command_tabs.values() if t.tab_index > 0]
        if not current_tabs:
            return
        selected_tab = [t for t in current_tabs if t.is_selected]
        if selected_tab:
            right_tab = [t for t in current_tabs if t.tab_index == selected_tab[0].tab_index + 1]
        else:
            right_tab = [t for t in current_tabs if t.tab_index == 1]
        if right_tab:
            self.tab_button_clicked(right_tab[0].name)

    def close_buton_clicked(self, command_name: str):
        self.command_tabs[command_name].button = None
        self.command_tabs[command_name].close_button = None
        self.command_tabs[command_name].output_field = None
        self.command_tabs[command_name].is_selected = False
        for tab in self.command_tabs.values():
            if tab.tab_index > self.command_tabs[command_name].tab_index:
                tab.tab_index -= 1
        self.command_tabs[command_name].tab_index = 0
        if self.command_tabs[command_name].task is not None:
            self.command_tabs[command_name].task.cancel()
            self.command_tabs[command_name].task = None
        self.redraw_app()

    def handle_tab_command(self, hummingbot: "HummingbotApplication", command_name: str, kwargs: Dict[str, Any]):
        if command_name not in self.command_tabs:
            return
        cmd_tab = self.command_tabs[command_name]
        if "close" in kwargs and kwargs["close"]:
            if cmd_tab.close_button is not None:
                self.close_buton_clicked(command_name)
            return
        if "close" in kwargs:
            kwargs.pop("close")
        if cmd_tab.button is None:
            cmd_tab.button = create_tab_button(command_name, lambda: self.tab_button_clicked(command_name))
            cmd_tab.close_button = create_tab_button("x", lambda: self.close_buton_clicked(command_name), 1, "", " ")
            cmd_tab.output_field = create_live_field()
            cmd_tab.tab_index = max(t.tab_index for t in self.command_tabs.values()) + 1
        self.tab_button_clicked(command_name)
        self.display_tab_output(cmd_tab, hummingbot, kwargs)

    def display_tab_output(self, command_tab: CommandTab, hummingbot: "HummingbotApplication", kwargs: Dict[Any, Any]):
        if command_tab.task is not None and not command_tab.task.done():
            return
        if threading.current_thread() != threading.main_thread():
            hummingbot.ev_loop.call_soon_threadsafe(self.display_tab_output, command_tab, hummingbot, kwargs)
            return
        command_tab.task = safe_ensure_future(
            command_tab.tab_class.display(command_tab.output_field, hummingbot, **kwargs)
        )

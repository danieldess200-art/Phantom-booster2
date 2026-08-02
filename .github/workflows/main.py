"""
DrexBoost — Network Check (v1, no-pyjnius build)
"""

import socket
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.properties import StringProperty, BooleanProperty
from kivy.clock import Clock
from kivy.lang import Builder


@dataclass
class ServerTarget:
    name: str
    host: str
    port: int = 443


@dataclass
class PingResult:
    name: str
    host: str
    samples_ms: list = field(default_factory=list)
    packet_loss_pct: float = 0.0

    @property
    def avg_ms(self):
        return round(statistics.mean(self.samples_ms), 1) if self.samples_ms else None

    @property
    def jitter_ms(self):
        if len(self.samples_ms) < 2:
            return None
        diffs = [abs(self.samples_ms[i] - self.samples_ms[i - 1]) for i in range(1, len(self.samples_ms))]
        return round(statistics.mean(diffs), 1)

    def __repr__(self):
        if not self.samples_ms:
            return f"{self.name} ({self.host}): unreachable, 100% loss"
        return f"{self.name}: avg={self.avg_ms}ms jitter={self.jitter_ms}ms loss={self.packet_loss_pct}%"


def tcp_ping_once(host, port, timeout=1.5):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - start) * 1000
    except (socket.timeout, OSError):
        return None


def ping_server(target, count=5, timeout=1.5, delay_between=0.2):
    result = PingResult(name=target.name, host=target.host)
    failures = 0
    for _ in range(count):
        latency = tcp_ping_once(target.host, target.port, timeout=timeout)
        if latency is not None:
            result.samples_ms.append(latency)
        else:
            failures += 1
        time.sleep(delay_between)
    result.packet_loss_pct = round((failures / count) * 100, 1)
    return result


def ping_all(targets, count=5):
    results = [ping_server(t, count=count) for t in targets]
    results.sort(key=lambda r: (r.avg_ms is None, r.avg_ms or float("inf")))
    return results


DEFAULT_TARGETS = [
    ServerTarget("Test - Cloudflare", "1.1.1.1", 443),
    ServerTarget("Test - Google", "8.8.8.8", 443),
]


@dataclass
class NetworkReport:
    servers: list
    best_server: Optional[PingResult]
    warnings: list = field(default_factory=list)

    def summary(self):
        lines = ["=== DrexBoost Network Check ===\n"]
        if self.best_server:
            lines.append(f"Best server: {self.best_server}")
        else:
            lines.append("No reachable servers found.")
        for s in self.servers:
            lines.append(f"  {s}")
        if self.warnings:
            lines.append("\n-- Warnings --")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


def run_check(targets=None, ping_count=5):
    targets = targets or DEFAULT_TARGETS
    server_results = ping_all(targets, count=ping_count)
    best = server_results[0] if server_results and server_results[0].avg_ms is not None else None

    warnings = []
    if best and best.jitter_ms is not None and best.jitter_ms > 30:
        warnings.append(f"High jitter on best server ({best.jitter_ms}ms) — may feel unstable mid-match.")
    if best and best.packet_loss_pct > 10:
        warnings.append(f"Noticeable packet loss ({best.packet_loss_pct}%) — expect rubberbanding.")

    return NetworkReport(servers=server_results, best_server=best, warnings=warnings)


class HomeScreen(Screen):
    status_text = StringProperty("Tap below to check your connection.")
    checking = BooleanProperty(False)

    def run_checklist(self):
        if self.checking:
            return
        self.checking = True
        self.status_text = "Checking connection..."
        Clock.schedule_once(self._do_check, 0.1)

    def _do_check(self, dt):
        report = run_check()
        self.checking = False
        self.manager.get_screen("result").load_report(report)
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "result"


class ResultScreen(Screen):
    summary_text = StringProperty("")
    ready_text = StringProperty("")
    ready_color = StringProperty("#888888")

    def load_report(self, report):
        self.summary_text = report.summary()
        if report.best_server:
            self.ready_text = "SERVER FOUND"
            self.ready_color = "#2ecc71"
        else:
            self.ready_text = "NO SERVER REACHABLE"
            self.ready_color = "#e74c3c"

    def go_home(self):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "home"


KV = """
<HomeScreen>:
    BoxLayout:
        orientation: "vertical"
        padding: 24
        spacing: 16
        Label:
            text: "DrexBoost"
            font_size: 32
            size_hint_y: None
            height: 60
        Label:
            text: root.status_text
            text_size: self.width, None
            halign: "center"
        Button:
            text: "Check Connection" if not root.checking else "Checking..."
            disabled: root.checking
            size_hint_y: None
            height: 72
            on_release: root.run_checklist()

<ResultScreen>:
    BoxLayout:
        orientation: "vertical"
        padding: 20
        spacing: 12
        Label:
            text: root.ready_text
            color: root.ready_color
            font_size: 22
            bold: True
            size_hint_y: None
            height: 40
        ScrollView:
            Label:
                text: root.summary_text
                text_size: self.width, None
                size_hint_y: None
                height: self.texture_size[1]
                halign: "left"
                valign: "top"
        Button:
            text: "Back"
            size_hint_y: None
            height: 56
            on_release: root.go_home()
"""


class DrexBoostApp(App):
    def build(self):
        Builder.load_string(KV)
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(ResultScreen(name="result"))
        return sm


if __name__ == "__main__":
    DrexBoostApp().run()

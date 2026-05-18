import subprocess
import time
import re
import psutil
from typing import Optional

class WatcherService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_pid(self, process_name: str) -> Optional[int]:
        for p in psutil.process_iter(['pid', 'cmdline']):
            if process_name in ' '.join(p.info['cmdline'] or []):
                return p.info['pid']
        return None

    def _tegrastats_line(self) -> str:
        out = subprocess.check_output(
            "tegrastats --interval 500 | head -n 1",
            shell=True, timeout=3
        )
        return out.decode().strip()

    def get_ram(self, process_name: Optional[str] = None) -> str:
        if process_name:
            pid = self._get_pid(process_name)
            if pid is None:
                return f"[{process_name}] introuvable"
            mem = psutil.Process(pid).memory_info().rss // (1024 * 1024)
            return f"{mem} MB"
        out = subprocess.check_output("free -m | grep Mem | awk '{print $3\"/\"$2}'", shell=True)
        return out.decode().strip()

    def get_vram(self, process_name: Optional[str] = None) -> str:
        if process_name:
            pid = self._get_pid(process_name)
            if pid is None:
                return f"[{process_name}] introuvable"
            # Lecture smaps pour GPU memory (approximatif sur Jetson unified memory)
            try:
                mem = psutil.Process(pid).memory_info().vms // (1024 * 1024)
                return f"~{mem} MB (vms)"
            except Exception:
                return "N/A"
        line = self._tegrastats_line()
        m = re.search(r'RAM (\d+)/(\d+)MB', line)
        return f"{m.group(1)}/{m.group(2)} MB" if m else "N/A"

    def get_cpu_gpu_usage(self, process_name: Optional[str] = None) -> tuple[str, str]:
        if process_name:
            pid = self._get_pid(process_name)
            if pid is None:
                return f"[{process_name}] introuvable", "N/A"
            cpu = psutil.Process(pid).cpu_percent(interval=0.5)
            # GPU par process non dispo nativement sur Jetson
            return f"{cpu:.1f}%", "N/A (global only)"

        line = self._tegrastats_line()
        cpu_match = re.search(r'CPU \[([^\]]+)\]', line)
        if cpu_match:
            percents = [int(x.split('%')[0]) for x in cpu_match.group(1).split(',')]
            cpu_avg = sum(percents) // len(percents)
        else:
            cpu_avg = 0
        gpu_match = re.search(r'GR3D_FREQ (\d+)%', line)
        gpu = int(gpu_match.group(1)) if gpu_match else 0
        return f"{cpu_avg}%", f"{gpu}%"

    def monitor_live(self, *process_names: str):
        try:
            first = True
            while True:
                lines = []

                ram = self.get_ram()
                vram = self.get_vram()
                cpu, gpu = self.get_cpu_gpu_usage()
                lines.append(f"[GLOBAL] RAM: {ram} Mo | VRAM: {vram} | CPU: {cpu} | GPU: {gpu}")

                for name in process_names:
                    p_ram = self.get_ram(name)
                    p_vram = self.get_vram(name)
                    p_cpu, p_gpu = self.get_cpu_gpu_usage(name)
                    lines.append(f"[{name}] RAM: {p_ram} | VRAM: {p_vram} | CPU: {p_cpu} | GPU: {p_gpu}")

                output = '\n'.join(lines)
                n = len(lines)

                if not first:
                    print(f"\033[{n}A\033[J", end='', flush=True)
                else:
                    first = False

                print(output, flush=True)
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nArrêt.")
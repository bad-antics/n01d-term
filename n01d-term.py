#!/usr/bin/env python3
"""
███╗   ██╗ ██████╗  ██╗██████╗       ████████╗███████╗██████╗ ███╗   ███╗
████╗  ██║██╔═████╗███║██╔══██╗      ╚══██╔══╝██╔════╝██╔══██╗████╗ ████║
██╔██╗ ██║██║██╔██║╚██║██║  ██║█████╗   ██║   █████╗  ██████╔╝██╔████╔██║
██║╚██╗██║████╔╝██║ ██║██║  ██║╚════╝   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║
██║ ╚████║╚██████╔╝ ██║██████╔╝         ██║   ███████╗██║  ██║██║ ╚═╝ ██║
╚═╝  ╚═══╝ ╚═════╝  ╚═╝╚═════╝          ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝

N01D Terminal - Modern terminal with hacker aesthetics
Part of the NullSec Toolkit
"""

import customtkinter as ctk
import subprocess
import threading
import os
import sys
import select
import pty
import signal
import struct
import fcntl
import termios
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List, Dict
import json
import re


VERSION = "1.0.0"
APP_NAME = "N01D Terminal"


class N01DTheme:
    """N01D hacker terminal theme"""
    
    def __init__(self):
        self.colors = {
            'bg_dark': '#0a0a0f',
            'bg': '#0d0d14',
            'bg_light': '#1a1a2e',
            'bg_lighter': '#252538',
            'accent': '#00ff88',
            'accent_dim': '#00cc66',
            'accent_hover': '#00dd77',
            'warning': '#ffaa00',
            'danger': '#ff3366',
            'info': '#00aaff',
            'text': '#e0e0e0',
            'text_dim': '#666666',
            'border': '#333344',
            # ANSI colors
            'ansi_black': '#1a1a2e',
            'ansi_red': '#ff5555',
            'ansi_green': '#00ff88',
            'ansi_yellow': '#ffaa00',
            'ansi_blue': '#00aaff',
            'ansi_magenta': '#ff79c6',
            'ansi_cyan': '#8be9fd',
            'ansi_white': '#e0e0e0',
        }
        
    def apply(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")


class CommandHistory:
    """Command history manager"""
    
    def __init__(self, max_size: int = 1000):
        self.history: List[str] = []
        self.position: int = 0
        self.max_size = max_size
        self.history_file = Path.home() / ".n01d-term-history"
        self._load()
        
    def _load(self):
        """Load history from file"""
        if self.history_file.exists():
            try:
                self.history = self.history_file.read_text().strip().split('\n')
                self.history = [h for h in self.history if h.strip()][-self.max_size:]
            except:
                self.history = []
        self.position = len(self.history)
        
    def _save(self):
        """Save history to file"""
        try:
            self.history_file.write_text('\n'.join(self.history[-self.max_size:]))
        except:
            pass
            
    def add(self, command: str):
        """Add command to history"""
        if command.strip() and (not self.history or self.history[-1] != command):
            self.history.append(command)
            self._save()
        self.position = len(self.history)
        
    def prev(self) -> Optional[str]:
        """Get previous command"""
        if self.position > 0:
            self.position -= 1
            return self.history[self.position]
        return None
        
    def next(self) -> Optional[str]:
        """Get next command"""
        if self.position < len(self.history) - 1:
            self.position += 1
            return self.history[self.position]
        elif self.position == len(self.history) - 1:
            self.position += 1
            return ""
        return None
        
    def search(self, prefix: str) -> List[str]:
        """Search history for commands starting with prefix"""
        return [h for h in reversed(self.history) if h.startswith(prefix)][:10]


class TerminalTab(ctk.CTkFrame):
    """Single terminal tab with PTY support"""
    
    def __init__(self, master, theme: N01DTheme, tab_name: str = "Terminal", **kwargs):
        super().__init__(master, **kwargs)
        
        self.theme = theme
        self.tab_name = tab_name
        self.history = CommandHistory()
        self.running = True
        
        # PTY
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        
        self.configure(fg_color=theme.colors['bg'])
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self._create_ui()
        self._start_shell()
        
    def _create_ui(self):
        """Create terminal UI"""
        # Output area
        self.output = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="JetBrains Mono", size=13),
            fg_color=self.theme.colors['bg'],
            text_color=self.theme.colors['text'],
            wrap="char",
            state="disabled"
        )
        self.output.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 0))
        
        # Configure tags for ANSI colors
        self._setup_tags()
        
        # Input area
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        input_frame.grid_columnconfigure(1, weight=1)
        
        # Prompt
        self.prompt_label = ctk.CTkLabel(
            input_frame,
            text=self._get_prompt(),
            font=ctk.CTkFont(family="JetBrains Mono", size=13, weight="bold"),
            text_color=self.theme.colors['accent']
        )
        self.prompt_label.grid(row=0, column=0, padx=(5, 2))
        
        # Command input
        self.input = ctk.CTkEntry(
            input_frame,
            font=ctk.CTkFont(family="JetBrains Mono", size=13),
            fg_color=self.theme.colors['bg_light'],
            border_width=0,
            height=35
        )
        self.input.grid(row=0, column=1, sticky="ew")
        
        # Bind keys
        self.input.bind("<Return>", self._on_enter)
        self.input.bind("<Up>", self._on_up)
        self.input.bind("<Down>", self._on_down)
        self.input.bind("<Tab>", self._on_tab)
        self.input.bind("<Control-c>", self._on_ctrl_c)
        self.input.bind("<Control-l>", self._on_ctrl_l)
        
        self.input.focus_set()
        
    def _setup_tags(self):
        """Setup text tags for ANSI colors"""
        self.output.configure(state="normal")
        
        # Basic colors
        colors = {
            'red': self.theme.colors['ansi_red'],
            'green': self.theme.colors['ansi_green'],
            'yellow': self.theme.colors['ansi_yellow'],
            'blue': self.theme.colors['ansi_blue'],
            'magenta': self.theme.colors['ansi_magenta'],
            'cyan': self.theme.colors['ansi_cyan'],
            'white': self.theme.colors['ansi_white'],
            'bold': self.theme.colors['text'],
            'dim': self.theme.colors['text_dim'],
        }
        
        for name, color in colors.items():
            self.output.tag_config(name, foreground=color)
            
        self.output.tag_config('bold', font=ctk.CTkFont(family="JetBrains Mono", size=13, weight="bold"))
        
        self.output.configure(state="disabled")
        
    def _get_prompt(self) -> str:
        """Generate shell prompt"""
        user = os.environ.get('USER', 'user')
        host = os.uname().nodename
        cwd = os.getcwd()
        home = str(Path.home())
        
        if cwd.startswith(home):
            cwd = "~" + cwd[len(home):]
            
        # Shorten if too long
        if len(cwd) > 30:
            parts = cwd.split('/')
            if len(parts) > 3:
                cwd = '/'.join(['...'] + parts[-2:])
                
        return f"┌──[N01D]─[{user}@{host}]─[{cwd}]\n└──╼ "
        
    def _start_shell(self):
        """Start shell process with PTY"""
        shell = os.environ.get('SHELL', '/bin/bash')
        
        # Create PTY
        self.pid, self.master_fd = pty.fork()
        
        if self.pid == 0:
            # Child process
            os.execv(shell, [shell, '-i'])
        else:
            # Parent process
            # Make non-blocking
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Start reader thread
            self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self.reader_thread.start()
            
    def _read_output(self):
        """Read output from PTY in background"""
        while self.running and self.master_fd:
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.1)
                if r:
                    data = os.read(self.master_fd, 4096)
                    if data:
                        self.after(0, lambda d=data: self._append_output(d.decode('utf-8', errors='replace')))
            except (OSError, ValueError):
                break
                
    def _append_output(self, text: str):
        """Append text to output with ANSI parsing"""
        self.output.configure(state="normal")
        
        # Simple ANSI parsing
        text = self._parse_ansi(text)
        
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")
        
    def _parse_ansi(self, text: str) -> str:
        """Strip ANSI codes (basic implementation)"""
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
        
    def _send_input(self, text: str):
        """Send input to shell"""
        if self.master_fd:
            try:
                os.write(self.master_fd, text.encode())
            except:
                pass
                
    def _on_enter(self, event=None):
        """Handle Enter key"""
        command = self.input.get()
        self.input.delete(0, 'end')
        
        # Add to history
        self.history.add(command)
        
        # Send to shell
        self._send_input(command + '\n')
        
        # Update prompt after command
        self.after(100, self._update_prompt)
        
        return "break"
        
    def _on_up(self, event=None):
        """Handle Up arrow - history"""
        prev = self.history.prev()
        if prev is not None:
            self.input.delete(0, 'end')
            self.input.insert(0, prev)
        return "break"
        
    def _on_down(self, event=None):
        """Handle Down arrow - history"""
        next_cmd = self.history.next()
        if next_cmd is not None:
            self.input.delete(0, 'end')
            self.input.insert(0, next_cmd)
        return "break"
        
    def _on_tab(self, event=None):
        """Handle Tab - completion"""
        # Basic path completion
        current = self.input.get()
        if current:
            parts = current.split()
            if parts:
                last = parts[-1]
                
                # Try to complete path
                try:
                    if '/' in last:
                        dir_path = os.path.dirname(last)
                        prefix = os.path.basename(last)
                    else:
                        dir_path = '.'
                        prefix = last
                        
                    if os.path.isdir(dir_path):
                        matches = [f for f in os.listdir(dir_path) if f.startswith(prefix)]
                        if len(matches) == 1:
                            completion = matches[0]
                            if '/' in last:
                                new_path = os.path.join(dir_path, completion)
                            else:
                                new_path = completion
                                
                            parts[-1] = new_path
                            self.input.delete(0, 'end')
                            self.input.insert(0, ' '.join(parts))
                        elif matches:
                            # Show matches
                            self._append_output('\n' + '  '.join(matches) + '\n')
                except:
                    pass
                    
        return "break"
        
    def _on_ctrl_c(self, event=None):
        """Handle Ctrl+C"""
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGINT)
            except:
                pass
        self.input.delete(0, 'end')
        return "break"
        
    def _on_ctrl_l(self, event=None):
        """Handle Ctrl+L - clear"""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        return "break"
        
    def _update_prompt(self):
        """Update the prompt"""
        self.prompt_label.configure(text=self._get_prompt())
        
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except:
                pass
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass


class QuickCommands(ctk.CTkFrame):
    """Quick command palette"""
    
    COMMANDS = [
        ("📊 System Info", "neofetch || fastfetch || screenfetch || uname -a"),
        ("💾 Disk Usage", "df -h"),
        ("🔄 Processes", "htop || top"),
        ("🌐 Network", "ip addr"),
        ("📁 Files", "ls -la"),
        ("🔍 Find", "find . -name '*.py' -type f 2>/dev/null | head -20"),
        ("📜 Git Status", "git status"),
        ("🐍 Python", "python3 --version"),
        ("🔧 Update", "sudo apt update"),
    ]
    
    def __init__(self, master, theme: N01DTheme, on_run: Callable, **kwargs):
        super().__init__(master, **kwargs)
        
        self.theme = theme
        self.on_run = on_run
        
        self.configure(fg_color=theme.colors['bg_light'], corner_radius=10)
        
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(
            header,
            text="⚡ Quick Commands",
            font=ctk.CTkFont(family="JetBrains Mono", size=11, weight="bold"),
            text_color=theme.colors['accent']
        ).pack(side="left")
        
        # Commands
        for name, cmd in self.COMMANDS:
            btn = ctk.CTkButton(
                self,
                text=name,
                font=ctk.CTkFont(family="JetBrains Mono", size=10),
                fg_color="transparent",
                hover_color=theme.colors['bg_lighter'],
                anchor="w",
                height=28,
                command=lambda c=cmd: on_run(c)
            )
            btn.pack(fill="x", padx=5, pady=1)


class N01DTerminal(ctk.CTk):
    """Main Terminal Application"""
    
    def __init__(self):
        super().__init__()
        
        self.theme = N01DTheme()
        self.theme.apply()
        
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("1200x800")
        self.minsize(800, 500)
        self.configure(fg_color=self.theme.colors['bg_dark'])
        
        # Tabs
        self.tabs: List[TerminalTab] = []
        self.current_tab: int = 0
        
        # Grid config
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self._create_header()
        self._create_sidebar()
        self._create_tab_bar()
        self._create_terminal_area()
        
        # Create first terminal
        self._new_tab()
        
        # Key bindings
        self.bind("<Control-t>", lambda e: self._new_tab())
        self.bind("<Control-w>", lambda e: self._close_current_tab())
        self.bind("<Control-Tab>", lambda e: self._next_tab())
        self.bind("<Control-Shift-Tab>", lambda e: self._prev_tab())
        
        # Cleanup on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _create_header(self):
        """Create header bar"""
        header = ctk.CTkFrame(self, fg_color=self.theme.colors['bg'], height=50, corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)
        
        # Logo
        logo = ctk.CTkLabel(
            header,
            text="N01D",
            font=ctk.CTkFont(family="JetBrains Mono", size=24, weight="bold"),
            text_color=self.theme.colors['accent']
        )
        logo.pack(side="left", padx=20)
        
        subtitle = ctk.CTkLabel(
            header,
            text="TERMINAL",
            font=ctk.CTkFont(family="JetBrains Mono", size=10),
            text_color=self.theme.colors['text_dim']
        )
        subtitle.pack(side="left", pady=5)
        
        # Time
        self.time_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(family="JetBrains Mono", size=12),
            text_color=self.theme.colors['text_dim']
        )
        self.time_label.pack(side="right", padx=20)
        self._update_time()
        
    def _update_time(self):
        """Update time display"""
        self.time_label.configure(text=datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._update_time)
        
    def _create_sidebar(self):
        """Create sidebar with quick commands"""
        sidebar = ctk.CTkFrame(self, fg_color=self.theme.colors['bg'], width=200, corner_radius=0)
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # Quick commands
        self.quick_cmds = QuickCommands(
            sidebar,
            self.theme,
            on_run=self._run_quick_command
        )
        self.quick_cmds.pack(fill="x", padx=10, pady=10)
        
        # Spacer
        ctk.CTkFrame(sidebar, fg_color="transparent").pack(fill="both", expand=True)
        
        # Session info
        info_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        info_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            info_frame,
            text=f"Shell: {os.path.basename(os.environ.get('SHELL', 'bash'))}",
            font=ctk.CTkFont(family="JetBrains Mono", size=9),
            text_color=self.theme.colors['text_dim']
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            info_frame,
            text=f"User: {os.environ.get('USER', 'unknown')}",
            font=ctk.CTkFont(family="JetBrains Mono", size=9),
            text_color=self.theme.colors['text_dim']
        ).pack(anchor="w")
        
    def _create_tab_bar(self):
        """Create tab bar"""
        self.tab_bar = ctk.CTkFrame(
            self,
            fg_color=self.theme.colors['bg_light'],
            height=35,
            corner_radius=0
        )
        self.tab_bar.grid(row=1, column=1, sticky="new")
        self.tab_bar.grid_propagate(False)
        
        self.tab_buttons_frame = ctk.CTkFrame(self.tab_bar, fg_color="transparent")
        self.tab_buttons_frame.pack(side="left", fill="y")
        
        # New tab button
        new_btn = ctk.CTkButton(
            self.tab_bar,
            text="+",
            width=30,
            height=25,
            font=ctk.CTkFont(size=16),
            fg_color="transparent",
            hover_color=self.theme.colors['accent'] + "40",
            command=self._new_tab
        )
        new_btn.pack(side="left", padx=5, pady=5)
        
    def _create_terminal_area(self):
        """Create main terminal area"""
        self.terminal_frame = ctk.CTkFrame(
            self,
            fg_color=self.theme.colors['bg'],
            corner_radius=0
        )
        self.terminal_frame.grid(row=1, column=1, sticky="nsew", pady=(35, 0))
        self.terminal_frame.grid_rowconfigure(0, weight=1)
        self.terminal_frame.grid_columnconfigure(0, weight=1)
        
    def _new_tab(self):
        """Create new terminal tab"""
        tab = TerminalTab(
            self.terminal_frame,
            self.theme,
            tab_name=f"Terminal {len(self.tabs) + 1}"
        )
        self.tabs.append(tab)
        
        self._update_tab_bar()
        self._switch_to_tab(len(self.tabs) - 1)
        
    def _close_tab(self, index: int):
        """Close a terminal tab"""
        if len(self.tabs) <= 1:
            return
            
        tab = self.tabs[index]
        tab.cleanup()
        tab.destroy()
        self.tabs.pop(index)
        
        if self.current_tab >= len(self.tabs):
            self.current_tab = len(self.tabs) - 1
            
        self._update_tab_bar()
        self._switch_to_tab(self.current_tab)
        
    def _close_current_tab(self):
        """Close current tab"""
        self._close_tab(self.current_tab)
        
    def _switch_to_tab(self, index: int):
        """Switch to a specific tab"""
        if 0 <= index < len(self.tabs):
            # Hide current
            for tab in self.tabs:
                tab.grid_forget()
                
            # Show selected
            self.current_tab = index
            self.tabs[index].grid(row=0, column=0, sticky="nsew")
            self.tabs[index].input.focus_set()
            
            self._update_tab_bar()
            
    def _next_tab(self):
        """Switch to next tab"""
        next_idx = (self.current_tab + 1) % len(self.tabs)
        self._switch_to_tab(next_idx)
        
    def _prev_tab(self):
        """Switch to previous tab"""
        prev_idx = (self.current_tab - 1) % len(self.tabs)
        self._switch_to_tab(prev_idx)
        
    def _update_tab_bar(self):
        """Update tab bar buttons"""
        for widget in self.tab_buttons_frame.winfo_children():
            widget.destroy()
            
        for i, tab in enumerate(self.tabs):
            frame = ctk.CTkFrame(self.tab_buttons_frame, fg_color="transparent")
            frame.pack(side="left", padx=2, pady=5)
            
            is_active = i == self.current_tab
            
            btn = ctk.CTkButton(
                frame,
                text=f"⬤ {tab.tab_name}",
                font=ctk.CTkFont(family="JetBrains Mono", size=11),
                fg_color=self.theme.colors['bg_lighter'] if is_active else "transparent",
                hover_color=self.theme.colors['bg_lighter'],
                width=120,
                height=25,
                command=lambda idx=i: self._switch_to_tab(idx)
            )
            btn.pack(side="left")
            
            close_btn = ctk.CTkButton(
                frame,
                text="×",
                font=ctk.CTkFont(size=14),
                width=20,
                height=25,
                fg_color="transparent",
                hover_color=self.theme.colors['danger'] + "40",
                command=lambda idx=i: self._close_tab(idx)
            )
            close_btn.pack(side="left")
            
    def _run_quick_command(self, command: str):
        """Run a quick command in current terminal"""
        if self.tabs:
            self.tabs[self.current_tab].input.delete(0, 'end')
            self.tabs[self.current_tab].input.insert(0, command)
            self.tabs[self.current_tab]._on_enter()
            
    def _on_close(self):
        """Clean up on close"""
        for tab in self.tabs:
            tab.cleanup()
        self.destroy()


def main():
    app = N01DTerminal()
    app.mainloop()
    

if __name__ == "__main__":
    main()

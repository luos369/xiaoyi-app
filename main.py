import flet as ft
import flet_audio as fta
import asyncio
import edge_tts
import os
import re
import time
import tempfile

# 移动端路径适配
SAVE_DIR = os.path.join(tempfile.gettempdir(), "xiaoyi_cache")
os.makedirs(SAVE_DIR, exist_ok=True)

VOICE_MAP = {
    "晓依 (活泼)": "zh-CN-XiaoyiNeural",
    "云希 (阳光)": "zh-CN-YunxiNeural",
    "晓晓 (温柔)": "zh-CN-XiaoxiaoNeural",
    "云泽 (沉稳)": "zh-CN-YunzeNeural"
}

SPEED_MAP = {
    "1.0x": "+0%", "1.2x": "+20%", "1.3x": "+30%", "1.4x": "+40%", 
    "1.5x": "+50%", "2.0x": "+100%", "2.5x": "+150%", "3.0x": "+200%"
}

async def main(page: ft.Page):
    page.title = "晓依听书"
    page.theme_mode = ft.ThemeMode.LIGHT
    
    # --- 状态与数据 ---
    state = {
        "idx": 0, "is_playing": False, "speed": "+0%", 
        "voice": "zh-CN-XiaoyiNeural", "book_path": "",
        "paragraphs": ["请点击右上角图标导入书籍"], 
        "chapters": [{"title": "暂无", "index": 0}],
        "sid": int(time.time())
    }

    # --- 进度存取 ---
    def load_prog(path): return page.client_storage.get(f"p_{path}") or 0
    def save_prog(path, i): page.client_storage.set(f"p_{path}", i)

    # --- 音频引擎 ---
    audio = fta.Audio(src="https://flet.dev/img/pages/components/audio/audio.mp3", autoplay=False)
    page.overlay.append(audio)
    play_event = asyncio.Event()
    audio.on_state_changed = lambda e: play_event.set() if e.data == "completed" else None

    # --- UI 组件 ---
    status_text = ft.Text("待机中", size=14, weight="bold")
    loading_ring = ft.ProgressRing(width=16, height=16, visible=False)
    
    ui_lines = [ft.Text("", opacity=0.3, text_align="center") for _ in range(3)] + \
               [ft.Text("", size=22, weight="bold", color=ft.Colors.BLUE_700, text_align="center")] + \
               [ft.Text("", opacity=0.3, text_align="center") for _ in range(3)]
    
    progress_slider = ft.Slider(min=0, max=1, on_change_end=lambda e: jump_to_index(state["chapters"][int(e.control.value)]["index"]))
    
    play_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_size=65, icon_color=ft.Colors.BLUE)
    prev_btn = ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, icon_size=40, icon_color=ft.Colors.BLUE_400)
    next_btn = ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, icon_size=40, icon_color=ft.Colors.BLUE_400)

    def update_ui():
        for i, line in enumerate(ui_lines):
            p_idx = state["idx"] + (i - 3)
            line.value = state["paragraphs"][p_idx] if 0 <= p_idx < len(state["paragraphs"]) else ""
        
        c_idx = next((i for i in range(len(state["chapters"])-1, -1, -1) if state["idx"] >= state["chapters"][i]["index"]), 0)
        progress_slider.value = c_idx
        if page.drawer: page.drawer.selected_index = c_idx
        status_text.value = f"📖 {state['chapters'][c_idx]['title']} ({state['idx']+1}/{len(state['paragraphs'])})"
        page.update()

    async def play_loop():
        sid = state["sid"]
        while state["is_playing"] and state["idx"] < len(state["paragraphs"]) and state["sid"] == sid:
            update_ui()
            f_path = os.path.join(SAVE_DIR, f"tts_{state['idx']}_{sid}.mp3")
            
            if not os.path.exists(f_path):
                loading_ring.visible = True; page.update()
                comm = edge_tts.Communicate(state["paragraphs"][state["idx"]], state["voice"], rate=state["speed"])
                await comm.save(f_path)
                loading_ring.visible = False; page.update()
            
            if os.path.exists(f_path) and state["is_playing"] and state["sid"] == sid:
                play_event.clear()
                audio.src = f_path
                page.update()
                audio.play()
                while not play_event.is_set() and state["is_playing"] and state["sid"] == sid:
                    await asyncio.sleep(0.1)
                if state["is_playing"] and state["sid"] == sid:
                    state["idx"] += 1
                    save_prog(state["book_path"], state["idx"])

    def toggle_play():
        if not state["book_path"]: return
        state["is_playing"] = not state["is_playing"]
        play_btn.icon = ft.Icons.PAUSE_CIRCLE_FILLED if state["is_playing"] else ft.Icons.PLAY_CIRCLE_FILL
        if state["is_playing"]:
            state["sid"] = int(time.time())
            page.run_task(play_loop)
        else: audio.pause()
        page.update()

    def jump_to_index(n_idx):
        state["idx"], state["sid"] = n_idx, int(time.time())
        save_prog(state["book_path"], n_idx)
        audio.pause(); update_ui()
        if state["is_playing"]: page.run_task(play_loop)

    def load_book(e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            state["book_path"] = path
            try:
                with open(path, 'r', encoding='utf-8') as f: lines = f.readlines()
            except:
                with open(path, 'r', encoding='gbk', errors='ignore') as f: lines = f.readlines()
            
            state["paragraphs"] = [p.strip() for p in lines if p.strip() and re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', p)]
            state["chapters"] = [{"title": p[:20], "index": i} for i, p in enumerate(state["paragraphs"]) 
                               if re.match(r'^\s*(?:###\s*)?第\s*[0-9一二三四五六七八九十百千万零]+\s*[章节回]', p)] or [{"title": "正文", "index": 0}]
            
            progress_slider.max = len(state["chapters"]) - 1
            progress_slider.divisions = len(state["chapters"]) - 1 if len(state["chapters"]) > 1 else 1
            state["idx"] = load_prog(path)
            
            # 更新侧边栏目录
            page.drawer.controls = [ft.Container(height=10), ft.Text("  小说目录", size=20, weight="bold")] + \
                                   [ft.NavigationDrawerDestination(label=c["title"], icon=ft.Icons.BOOKMARK) for c in state["chapters"]]
            update_ui()

    picker = ft.FilePicker(on_result=load_book)
    page.overlay.append(picker)

    # 🌟 侧边栏
    page.drawer = ft.NavigationDrawer(
        on_change=lambda e: [jump_to_index(state["chapters"][e.control.selected_index]["index"]), setattr(page.drawer, "open", False), page.update()],
        controls=[ft.Text("请先导入书籍", size=20)]
    )

    page.appbar = ft.AppBar(
        leading=ft.IconButton(ft.Icons.MENU, on_click=lambda _: [setattr(page.drawer, "open", True), page.update()]),
        title=ft.Text("晓依听书"),
        actions=[ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.pick_files(allowed_extensions=["txt"])), loading_ring]
    )

    page.add(
        ft.Column(ui_lines, expand=True, alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        ft.Column([
            ft.Row([status_text], alignment="center"),
            progress_slider,
            ft.Row([
                ft.PopupMenuButton(content=ft.Text("音色", weight="bold"), items=[ft.PopupMenuItem(text=k, on_click=lambda e: [setattr(state, "voice", VOICE_MAP[e.control.text]), jump_to_index(state["idx"])]) for k in VOICE_MAP.keys()]),
                ft.Row([prev_btn, play_btn, next_btn], spacing=5),
                ft.PopupMenuButton(content=ft.Text("倍速", weight="bold"), items=[ft.PopupMenuItem(text=k, on_click=lambda e: [setattr(state, "speed", SPEED_MAP[e.control.text]), jump_to_index(state["idx"])]) for k in SPEED_MAP.keys()]),
            ], alignment="center", spacing=20)
        ], spacing=10)
    )
    # 绑定切章逻辑
    prev_btn.on_click = lambda _: jump_to_index(state["chapters"][max(0, next(i for i in range(len(state["chapters"])-1, -1, -1) if state["idx"] >= state["chapters"][i]["index"])-1)]["index"])
    next_btn.on_click = lambda _: jump_to_index(state["chapters"][min(len(state["chapters"])-1, next(i for i in range(len(state["chapters"])-1, -1, -1) if state["idx"] >= state["chapters"][i]["index"])+1)]["index"])
    update_ui()

ft.app(target=main)

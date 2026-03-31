import flet as ft
import flet_audio as fta
import asyncio
import edge_tts
import os
import json
import re
import time
import tempfile

# 自动获取手机系统的安全临时目录
SAVE_DIR = os.path.join(tempfile.gettempdir(), "xiaoyi_cache")
os.makedirs(SAVE_DIR, exist_ok=True)

# 音色与倍速配置
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

def is_valid_text(text):
    return bool(re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', text))

async def synthesize(text, filepath, speed, voice):
    tmp_filepath = filepath + ".tmp"
    try:
        comm = edge_tts.Communicate(text, voice, rate=speed)
        await comm.save(tmp_filepath)
        if os.path.exists(filepath): os.remove(filepath)
        os.rename(tmp_filepath, filepath)
        return True
    except:
        return False

async def main(page: ft.Page):
    page.title = "晓依听书"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20

    # 核心状态
    book = {"path": "", "paragraphs": ["请点击右上角图标导入书籍"], "chapters": [{"title": "暂无", "index": 0}]}
    state = {
        "idx": 0, "is_playing": False, "speed": "+0%", 
        "voice": "zh-CN-XiaoyiNeural", "sid": int(time.time()), "is_loading": False
    }

    # 原生音频组件
    audio = fta.Audio(src="https://flet.dev/img/pages/components/audio/audio.mp3", autoplay=False)
    page.overlay.append(audio)
    play_event = asyncio.Event()
    audio.on_state_changed = lambda e: play_event.set() if e.data == "completed" else None

    # UI 文本行
    ui_lines = [ft.Text("", opacity=0.3, text_align="center") for _ in range(3)] + \
               [ft.Text("", size=22, weight="bold", color=ft.Colors.BLUE_700, text_align="center")] + \
               [ft.Text("", opacity=0.3, text_align="center") for _ in range(3)]
    
    status_text = ft.Text("待机中", size=14, weight="bold")
    loading_ring = ft.ProgressRing(width=16, height=16, visible=False)
    
    progress_slider = ft.Slider(min=0, max=1, on_change_end=lambda e: jump_to_index(book["chapters"][int(e.control.value)]["index"]))
    
    play_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_size=65, on_click=lambda _: toggle_play())

    def update_ui():
        for i, line in enumerate(ui_lines):
            p_idx = state["idx"] + (i - 3)
            line.value = book["paragraphs"][p_idx] if 0 <= p_idx < len(book["paragraphs"]) else ""
        
        c_idx = next((i for i in range(len(book["chapters"])-1, -1, -1) if state["idx"] >= book["chapters"][i]["index"]), 0)
        progress_slider.value = c_idx
        status_text.value = f"📖 {book['chapters'][c_idx]['title']} ({state['idx']+1}/{len(book['paragraphs'])})"
        page.update()

    async def play_loop():
        sid = state["sid"]
        while state["is_playing"] and state["idx"] < len(book["paragraphs"]) and state["sid"] == sid:
            update_ui()
            f_path = os.path.join(SAVE_DIR, f"tts_{state['idx']}_{sid}.mp3")
            
            if not os.path.exists(f_path):
                loading_ring.visible = True; page.update()
                await synthesize(book["paragraphs"][state["idx"]], f_path, state["speed"], state["voice"])
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

    def toggle_play():
        if not book["path"]: return
        state["is_playing"] = not state["is_playing"]
        play_btn.icon = ft.Icons.PAUSE_CIRCLE_FILLED if state["is_playing"] else ft.Icons.PLAY_CIRCLE_FILL
        if state["is_playing"]:
            state["sid"] = int(time.time())
            page.run_task(play_loop)
        else:
            audio.pause()
        page.update()

    def jump_to_index(n_idx):
        state["idx"], state["sid"] = n_idx, int(time.time())
        audio.pause(); update_ui()
        if state["is_playing"]: page.run_task(play_loop)

    def load_book(e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            book["path"] = path
            try:
                with open(path, 'r', encoding='utf-8') as f: lines = f.readlines()
            except:
                with open(path, 'r', encoding='gbk', errors='ignore') as f: lines = f.readlines()
            
            book["paragraphs"] = [p.strip() for p in lines if p.strip() and is_valid_text(p)]
            book["chapters"] = [{"title": p[:20], "index": i} for i, p in enumerate(book["paragraphs"]) 
                               if re.match(r'^\s*(?:###\s*)?第\s*[0-9一二三四五六七八九十百千万零]+\s*[章节回]', p)] or [{"title": "正文", "index": 0}]
            
            progress_slider.max = len(book["chapters"]) - 1
            progress_slider.divisions = len(book["chapters"]) - 1 if len(book["chapters"]) > 1 else 1
            state["idx"] = 0
            update_ui()

    picker = ft.FilePicker(on_result=load_book)
    page.overlay.append(picker)

    # 顶部栏
    page.appbar = ft.AppBar(
        title=ft.Text("晓依听书"),
        actions=[
            ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.pick_files(allowed_extensions=["txt"])),
            loading_ring, ft.Container(width=10)
        ]
    )

    # 布局
    page.add(
        ft.Column(ui_lines, expand=True, alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        ft.Column([
            ft.Row([status_text], alignment="center"),
            progress_slider,
            ft.Row([
                ft.PopupMenuButton(
                    content=ft.Text("音色", weight="bold"),
                    items=[ft.PopupMenuItem(text=k, on_click=lambda e: [setattr(state, "voice", VOICE_MAP[e.control.text]), jump_to_index(state["idx"])]) for k in VOICE_MAP.keys()]
                ),
                play_btn,
                ft.PopupMenuButton(
                    content=ft.Text("倍速", weight="bold"),
                    items=[ft.PopupMenuItem(text=k, on_click=lambda e: [setattr(state, "speed", SPEED_MAP[e.control.text]), jump_to_index(state["idx"])]) for k in SPEED_MAP.keys()]
                ),
            ], alignment="center", spacing=30)
        ], spacing=10)
    )

ft.app(target=main)

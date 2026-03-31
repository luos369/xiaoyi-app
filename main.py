import flet as ft
import flet_audio as fta
import asyncio
import edge_tts
import os
import json
import re
import time
import tempfile

# --- 移动端路径适配 ---
SAVE_DIR = os.path.join(tempfile.gettempdir(), "xiaoyi_cache")
PROGRESS_FILE = os.path.join(SAVE_DIR, "reading_progress.json")
CACHE_AHEAD = 10  

VOICE_MAP = {
    "晓依 (活女)": "zh-CN-XiaoyiNeural",
    "云希 (阳光)": "zh-CN-YunxiNeural",
    "晓晓 (温柔)": "zh-CN-XiaoxiaoNeural",
    "云泽 (沉稳)": "zh-CN-YunzeNeural"
}

SPEED_MAP = {
    "1.0x": "+0%", "1.2x": "+20%", "1.3x": "+30%", "1.4x": "+40%", 
    "1.5x": "+50%", "2.0x": "+100%", "2.5x": "+150%", "3.0x": "+200%"
}

os.makedirs(SAVE_DIR, exist_ok=True)

def load_progress(book_path):
    if not book_path: return 0
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get(book_path, 0)
        except: return 0
    return 0

def save_progress(book_path, index):
    if not book_path: return
    data = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except: pass
    data[book_path] = index
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)

def is_valid_text(text):
    return bool(re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', text))

async def synthesize(text, filepath, speed, voice):
    tmp_filepath = filepath + ".tmp"
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice, rate=speed)
            await comm.save(tmp_filepath)
            if os.path.exists(filepath): os.remove(filepath)
            os.rename(tmp_filepath, filepath)
            return True
        except Exception:
            await asyncio.sleep(0.5)
    return False

def main(page: ft.Page):
    page.title = "晓依听书"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    book = {"path": "", "paragraphs": ["请点击右上角图标导入书籍"], "total": 1, "chapters": [{"title": "暂无", "index": 0}]}
    state = {"idx": 0, "is_playing": False, "is_changing_slider": False, "speed_rate": "+0%", "voice": "zh-CN-XiaoyiNeural", "session_id": int(time.time())}

    audio = fta.Audio(autoplay=False)
    page.overlay.append(audio)
    play_event = asyncio.Event()
    audio.on_state_changed = lambda e: play_event.set() if e.data == "completed" else None

    # UI
    status_text = ft.Text("未加载", size=14, weight="bold")
    loading_ring = ft.ProgressRing(width=16, height=16, visible=False)
    ui_lines = [ft.Text("", opacity=0.3) for _ in range(3)] + [ft.Text("", size=22, weight="bold", color=ft.Colors.BLUE_700)] + [ft.Text("", opacity=0.3) for _ in range(3)]
    progress_slider = ft.Slider(min=0, max=1, on_change_end=lambda e: jump_to_index(book["chapters"][int(e.control.value)]["index"]))
    play_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_size=65, on_click=lambda _: toggle_play())

    def update_ui():
        for i, line in enumerate(ui_lines):
            p_idx = state["idx"] + (i - 3)
            line.value = book["paragraphs"][p_idx] if 0 <= p_idx < book["total"] else ""
        c_idx = next((i for i in range(len(book["chapters"])-1, -1, -1) if state["idx"] >= book["chapters"][i]["index"]), 0)
        if not state["is_changing_slider"]: progress_slider.value = c_idx
        status_text.value = f"📖 {book['chapters'][c_idx]['title']}"
        page.update()

    def jump_to_index(n_idx):
        state["idx"], state["session_id"] = n_idx, int(time.time())
        save_progress(book["path"], n_idx)
        audio.pause(); update_ui()
        if state["is_playing"]: page.run_task(background_cacher); page.run_task(play_loop)

    async def play_loop():
        sid = state["session_id"]
        while state["is_playing"] and state["idx"] < book["total"] and state["session_id"] == sid:
            cur_idx = state["idx"]
            f_path = os.path.join(SAVE_DIR, f"tts_{cur_idx}_{sid}.mp3")
            loading_ring.visible = True; page.update()
            while not os.path.exists(f_path):
                if not state["is_playing"] or state["session_id"] != sid: return
                await asyncio.sleep(0.2)
            loading_ring.visible = False; play_event.clear()
            audio.src = f_path; page.update(); audio.play()
            while not play_event.is_set() and state["is_playing"] and state["session_id"] == sid:
                await asyncio.sleep(0.1)
            if state["is_playing"] and state["idx"] == cur_idx:
                state["idx"] += 1; save_progress(book["path"], state["idx"]); update_ui()

    async def background_cacher():
        sid = state["session_id"]
        while state["is_playing"] and state["session_id"] == sid:
            for i in range(CACHE_AHEAD):
                t_idx = state["idx"] + i
                if t_idx >= book["total"] or state["session_id"] != sid: break
                f = os.path.join(SAVE_DIR, f"tts_{t_idx}_{sid}.mp3")
                if not os.path.exists(f):
                    await synthesize(book["paragraphs"][t_idx], f, state["speed_rate"], state["voice"])
            await asyncio.sleep(1)

    def toggle_play():
        if not book["path"]: return
        state["is_playing"] = not state["is_playing"]
        play_btn.icon = ft.Icons.PAUSE_CIRCLE_FILLED if state["is_playing"] else ft.Icons.PLAY_CIRCLE_FILL
        if state["is_playing"]:
            state["session_id"] = int(time.time())
            page.run_task(background_cacher); page.run_task(play_loop)
        else: audio.pause()
        page.update()

    def load_book(path):
        book["path"] = path
        try:
            with open(path, 'r', encoding='utf-8') as f: lines = f.readlines()
        except:
            with open(path, 'r', encoding='gbk', errors='ignore') as f: lines = f.readlines()
        book["paragraphs"] = [p.strip() for p in lines if p.strip() and is_valid_text(p)]
        book["total"] = len(book["paragraphs"])
        book["chapters"] = [{"title": p[:20], "index": i} for i, p in enumerate(book["paragraphs"]) if re.match(r'^\s*(?:###\s*)?第\s*[0-9一二三四五六七八九十百千万零]+\s*[章节卷回]', p)] or [{"title": "正文", "index": 0}]
        state["idx"] = load_progress(path)
        progress_slider.max = len(book["chapters"]) - 1
        update_ui()

    picker = ft.FilePicker(on_result=lambda e: load_book(e.files[0].path) if e.files else None)
    page.overlay.append(picker)
    page.appbar = ft.AppBar(title=ft.Text("晓依听书"), actions=[ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: picker.pick_files(allowed_extensions=["txt"])), loading_ring])
    page.add(ft.Column(ui_lines, expand=True, alignment=ft.MainAxisAlignment.CENTER), ft.Divider(), ft.Column([ft.Row([status_text], alignment="center"), progress_slider, ft.Row([play_btn], alignment="center")], spacing=5))
    update_ui()

ft.app(target=main)

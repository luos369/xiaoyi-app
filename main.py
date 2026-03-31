import flet as ft
import pygame
import asyncio
import edge_tts
import os
import json
import re
import time
import tempfile

# --- 配置区 ---
# 获取手机/电脑系统的安全临时目录
SAVE_DIR = os.path.join(tempfile.gettempdir(), "xiaoyi_cache")
PROGRESS_FILE = os.path.join(SAVE_DIR, "reading_progress.json")
CACHE_AHEAD = 10  # 移动端推荐缓存 10 段即可

# 🌟 新增：四大神仙音色库
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
        except:
            return 0
    return 0


def save_progress(book_path, index):
    if not book_path: return
    data = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass
    data[book_path] = index
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def is_valid_text(text):
    return bool(re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', text))


# 🌟 核心引擎：增加 voice 参数
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


# --- 主界面 ---
def main(page: ft.Page):
    page.title = "晓依听书"
    page.window_width = 450
    page.window_height = 850
    page.theme_mode = ft.ThemeMode.LIGHT
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    pygame.mixer.init()

    book = {
        "path": "",
        "paragraphs": ["请点击右上角 📁 图标，选择本地 TXT 小说文件开始听书。"],
        "total": 1,
        "chapters": [{"title": "暂无书籍", "index": 0}]
    }

    state = {
        "idx": 0,
        "is_playing": False,
        "is_changing_slider": False,
        "speed_rate": SPEED_MAP["1.0x"],
        "voice": VOICE_MAP["晓依 (活女)"],  # 默认音色
        "session_id": int(time.time() * 1000)
    }

    def get_current_chapter_idx(para_idx):
        for i in range(len(book["chapters"]) - 1, -1, -1):
            if para_idx >= book["chapters"][i]["index"]: return i
        return 0

    # UI 组件
    status_text = ft.Text("未加载书籍", color=ft.Colors.GREY_600, size=14, weight="bold")
    loading_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    ui_lines = [ft.Text("", text_align="center", opacity=0.3) for _ in range(3)] + \
               [ft.Text("", size=22, weight="bold", color=ft.Colors.BLUE_700, text_align="center")] + \
               [ft.Text("", text_align="center", opacity=0.3) for _ in range(3)]

    progress_slider = ft.Slider(
        min=0, max=1, divisions=1, label="第 {value} 章",
        on_change_start=lambda _: setattr(state, "is_changing_slider", True),
        on_change_end=lambda e: jump_to_index(book["chapters"][int(e.control.value)]["index"])
    )

    play_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_size=65, icon_color=ft.Colors.BLUE)
    prev_btn = ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, icon_size=40, icon_color=ft.Colors.BLUE_400)
    next_btn = ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, icon_size=40, icon_color=ft.Colors.BLUE_400)

    speed_text = ft.Text("1.0x", size=15, weight="bold", color=ft.Colors.BLUE_700)
    voice_text = ft.Text("晓依", size=15, weight="bold", color=ft.Colors.BLUE_700)  # 音色按钮文字

    def load_new_book(filepath):
        if not os.path.exists(filepath): return

        state["is_playing"] = False
        play_btn.icon = ft.Icons.PLAY_CIRCLE_FILL
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        state["session_id"] = int(time.time() * 1000)

        book["path"] = filepath
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                raw_lines = f.readlines()

        book["paragraphs"] = [p.strip() for p in raw_lines if p.strip() and is_valid_text(p)]
        book["total"] = len(book["paragraphs"])
        if book["total"] == 0:
            book["paragraphs"] = ["该文件内容为空。"];
            book["total"] = 1

        book["chapters"].clear()
        chapter_pattern = r'^\s*(?:###\s*)?第\s*[0-9一二三四五六七八九十百千万零]+\s*[章节卷回]'
        for i, p in enumerate(book["paragraphs"]):
            if re.match(chapter_pattern, p):
                book["chapters"].append({"title": p.replace('#', '').strip()[:20], "index": i})
        if not book["chapters"]:
            book["chapters"].append({"title": "正文", "index": 0})

        state["idx"] = load_progress(book["path"])

        slider_max = max(1, len(book["chapters"]) - 1)
        progress_slider.max = slider_max
        progress_slider.divisions = slider_max

        page.drawer.controls = [ft.Container(height=10), ft.Text("  小说目录", size=20, weight="bold")] + \
                               [ft.NavigationDrawerDestination(label=c["title"], icon=ft.Icons.BOOKMARK) for c in
                                book["chapters"]]

        book_name = os.path.basename(filepath)
        page.title = book_name
        page.appbar.title.value = book_name[:12] + ("..." if len(book_name) > 12 else "")
        update_ui()

    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            load_new_book(e.files[0].path)

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    def update_ui():
        for i, ui_line in enumerate(ui_lines):
            offset = i - 3
            para_idx = state["idx"] + offset
            ui_line.value = book["paragraphs"][para_idx] if 0 <= para_idx < book["total"] else ""

        curr_chap_idx = get_current_chapter_idx(state["idx"])
        if page.drawer: page.drawer.selected_index = curr_chap_idx
        if not state["is_changing_slider"]: progress_slider.value = curr_chap_idx

        status_text.value = f"📖 {book['chapters'][curr_chap_idx]['title']} ({state['idx'] + 1}/{book['total']})"
        page.update()

    # 🌟 万能重启函数：用于切章、切倍速、切音色
    def restart_playback(new_idx=None):
        if new_idx is not None:
            state["idx"] = new_idx
            save_progress(book["path"], new_idx)

        state["is_changing_slider"] = False
        state["session_id"] = int(time.time() * 1000)
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        update_ui()
        if state["is_playing"]:
            page.run_task(background_cacher)
            page.run_task(play_loop)

    def jump_to_index(new_idx):
        if not book["path"]: return
        restart_playback(new_idx)

    def go_prev_chapter(e):
        curr_chap_idx = get_current_chapter_idx(state["idx"])
        jump_to_index(book["chapters"][curr_chap_idx - 1]["index"] if curr_chap_idx > 0 else 0)

    def go_next_chapter(e):
        curr_chap_idx = get_current_chapter_idx(state["idx"])
        if curr_chap_idx < len(book["chapters"]) - 1:
            jump_to_index(book["chapters"][curr_chap_idx + 1]["index"])

    prev_btn.on_click = go_prev_chapter
    next_btn.on_click = go_next_chapter

    # 倍速切换逻辑
    def on_speed_select(e):
        new_speed = e.control.text
        if speed_text.value == new_speed: return
        speed_text.value = new_speed
        state["speed_rate"] = SPEED_MAP[new_speed]
        page.update()
        if state["is_playing"]: restart_playback()

    speed_menu = ft.PopupMenuButton(
        content=ft.Row([ft.Icon(ft.Icons.SPEED, size=18, color=ft.Colors.BLUE_700), speed_text], spacing=2),
        items=[ft.PopupMenuItem(text=k, on_click=on_speed_select) for k in SPEED_MAP.keys()]
    )

    # 🌟 新增：音色切换逻辑
    def on_voice_select(e):
        new_voice_key = e.control.text
        # 提取括号前的名字显示在按钮上
        short_name = new_voice_key.split(" ")[0]
        if voice_text.value == short_name: return

        voice_text.value = short_name
        state["voice"] = VOICE_MAP[new_voice_key]
        page.update()
        if state["is_playing"]: restart_playback()

    voice_menu = ft.PopupMenuButton(
        content=ft.Row([ft.Icon(ft.Icons.RECORD_VOICE_OVER, size=18, color=ft.Colors.BLUE_700), voice_text], spacing=2),
        items=[ft.PopupMenuItem(text=k, on_click=on_voice_select) for k in VOICE_MAP.keys()]
    )

    page.drawer = ft.NavigationDrawer(
        on_change=lambda e: [jump_to_index(book["chapters"][e.control.selected_index]["index"]),
                             setattr(page.drawer, "open", False), page.update()],
        controls=[ft.Container(height=10), ft.Text("  小说目录", size=20, weight="bold")]
    )

    async def background_cacher():
        my_session = state["session_id"]
        while state["is_playing"] and state["session_id"] == my_session:
            done = True
            for offset in range(CACHE_AHEAD):
                if state["session_id"] != my_session: return
                t_idx = state["idx"] + offset
                if t_idx >= book["total"]: break
                f_path = os.path.join(SAVE_DIR, f"tts_{t_idx}_{my_session}.mp3")
                if not (os.path.exists(f_path) and os.path.getsize(f_path) > 0):
                    done = False
                    # 传入当前选定的倍速和音色
                    await synthesize(book["paragraphs"][t_idx], f_path, state["speed_rate"], state["voice"])
                    break
            await asyncio.sleep(1.0 if done else 0.05)

    async def play_loop():
        my_session = state["session_id"]
        while state["is_playing"] and state["idx"] < book["total"] and state["session_id"] == my_session:
            s_idx = state["idx"]
            update_ui()
            f_path = os.path.join(SAVE_DIR, f"tts_{s_idx}_{my_session}.mp3")

            loading_ring.visible = True;
            page.update()
            while not os.path.exists(f_path) or os.path.getsize(f_path) == 0:
                if not state["is_playing"] or state["session_id"] != my_session: return
                await asyncio.sleep(0.1)
            loading_ring.visible = False;
            page.update()

            try:
                pygame.mixer.music.load(f_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and state["is_playing"] and state["session_id"] == my_session:
                    await asyncio.sleep(0.1)
            except:
                pass
            pygame.mixer.music.stop();
            pygame.mixer.music.unload()

            if state["is_playing"] and state["idx"] == s_idx and state["session_id"] == my_session:
                state["idx"] += 1
                save_progress(book["path"], state["idx"])

                def cleanup():
                    for f in os.listdir(SAVE_DIR):
                        if f.startswith("tts_"):
                            try:
                                parts = f.replace(".mp3", "").split("_")
                                if int(parts[2]) != state["session_id"] or int(parts[1]) < state["idx"] - 2:
                                    os.remove(os.path.join(SAVE_DIR, f))
                            except:
                                pass

                asyncio.create_task(asyncio.to_thread(cleanup))

        if not state["is_playing"] and state["session_id"] == my_session:
            play_btn.icon = ft.Icons.PLAY_CIRCLE_FILL;
            page.update()

    def toggle_play(e):
        if not book["path"]: return
        if not state["is_playing"]:
            state["is_playing"] = True
            play_btn.icon = ft.Icons.PAUSE_CIRCLE_FILLED
            state["session_id"] = int(time.time() * 1000)
            page.update()
            page.run_task(background_cacher)
            page.run_task(play_loop)
        else:
            state["is_playing"] = False
            play_btn.icon = ft.Icons.PLAY_CIRCLE_FILL
            pygame.mixer.music.stop()
            page.update()

    play_btn.on_click = toggle_play

    page.appbar = ft.AppBar(
        leading=ft.IconButton(ft.Icons.MENU, on_click=lambda _: [setattr(page.drawer, "open", True), page.update()]),
        title=ft.Text("晓依听书", size=18, weight="bold"),
        actions=[
            ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="导入本地小说",
                          on_click=lambda _: file_picker.pick_files(allowed_extensions=["txt"])),
            loading_ring,
            ft.Container(width=10)
        ]
    )

    # 🌟 底部控制栏完美排版：音色 - 控制台 - 倍速
    page.add(
        ft.Column(ui_lines, spacing=15, expand=True, alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        ft.Column([
            ft.Row([status_text], alignment=ft.MainAxisAlignment.CENTER),
            progress_slider,
            ft.Row([
                ft.Container(content=voice_menu, width=80, alignment=ft.alignment.center_left),
                ft.Row([prev_btn, play_btn, next_btn], spacing=5),
                ft.Container(content=speed_menu, width=80, alignment=ft.alignment.center_right)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=5)
    )
    update_ui()


if __name__ == "__main__":
    for f in os.listdir(SAVE_DIR):
        if f.startswith("tts_") or f.endswith(".tmp"):
            try:
                os.remove(os.path.join(SAVE_DIR, f))
            except:
                pass
    ft.app(target=main)
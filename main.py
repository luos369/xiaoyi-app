import flet as ft
import asyncio
import edge_tts
import os
import json
import re
import time
import tempfile

# --- 配置区 ---
# 自动识别系统缓存目录，增加严格的容错和判空机制
def get_save_dir():
    try:
        base_dir = tempfile.gettempdir()
        path = os.path.join(base_dir, "xiaoyi_cache")
    except Exception:
        # 如果获取系统临时目录失败，则存放在当前安全目录下
        path = os.path.join(os.getcwd(), "xiaoyi_cache")
        
    if not os.path.exists(path):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            # 终极保底：如果无法新建文件夹，直接使用当前目录
            return os.getcwd()
    return path

SAVE_DIR = get_save_dir()
PROGRESS_FILE = os.path.join(SAVE_DIR, "reading_progress.json")
CACHE_AHEAD = 5

VOICE_MAP = {
    "晓依 (活女)": "zh-CN-XiaoyiNeural",
    "云希 (阳光)": "zh-CN-YunxiNeural",
    "晓晓 (温柔)": "zh-CN-XiaoxiaoNeural",
    "云泽 (沉稳)": "zh-CN-YunzeNeural"
}

SPEED_MAP = {
    "1.0x": "+0%", "1.2x": "+20%", "1.3x": "+30%", "1.5x": "+40%",
    "1.5x": "+50%", "2.0x": "+100%", "2.5x": "+150%", "3.0x": "+200%"
}

# --- 核心逻辑 ---
async def synthesize(text, filepath, speed, voice):
    tmp_filepath = filepath + ".tmp"
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True
    try:
        comm = edge_tts.Communicate(text, voice, rate=speed)
        await comm.save(tmp_filepath)
        if os.path.exists(filepath): os.remove(filepath)
        os.rename(tmp_filepath, filepath)
        return True
    except:
        return False

def main(page: ft.Page):
    page.title = "晓依听书"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
    # 初始化原生音频
    audio_player = ft.Audio(src="", autoplay=False)
    page.overlay.append(audio_player)

    # 数据状态
    book = {
        "path": "",
        "paragraphs": ["请点击右上角文件夹图标导入 TXT 小说。"],
        "total": 1,
        "chapters": [{"title": "暂无书籍", "index": 0}]
    }

    state = {
        "idx": 0,
        "is_playing": False,
        "speed_rate": SPEED_MAP["1.0x"],
        "voice": VOICE_MAP["晓依 (活女)"],
        "session_id": int(time.time() * 1000)
    }

    # UI 组件
    status_text = ft.Text("未加载", size=12, color=ft.Colors.GREY_700)
    loading_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
    
    ui_lines = [ft.Text("", text_align="center", opacity=0.4, size=14) for _ in range(3)] + \
               [ft.Text("晓依听书", size=22, weight="bold", color=ft.Colors.BLUE_800, text_align="center")] + \
               [ft.Text("", text_align="center", opacity=0.4, size=14) for _ in range(3)]

    progress_slider = ft.Slider(min=0, max=1, divisions=1, value=0)
    play_btn = ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_size=60, icon_color=ft.Colors.BLUE)

    def update_ui():
        # 更新文本滚动
        for i, ui_line in enumerate(ui_lines):
            offset = i - 3
            curr_idx = state["idx"] + offset
            if 0 <= curr_idx < len(book["paragraphs"]):
                ui_line.value = book["paragraphs"][curr_idx]
            else:
                ui_line.value = ""
        
        # 更新进度条和状态
        total = book["total"]
        status_text.value = f"进度: {state['idx'] + 1} / {total}"
        page.update()

    async def play_loop():
        current_session = state["session_id"]
        while state["is_playing"] and state["idx"] < book["total"] and state["session_id"] == current_session:
            idx = state["idx"]
            f_path = os.path.join(SAVE_DIR, f"tts_{idx}_{current_session}.mp3")
            
            # 等待文件缓存
            wait_count = 0
            while not os.path.exists(f_path):
                if not state["is_playing"] or state["session_id"] != current_session: return
                loading_ring.visible = True
                page.update()
                await asyncio.sleep(0.5)
                wait_count += 1
                if wait_count > 20: break # 超时保护
            
            loading_ring.visible = False
            update_ui()
            
            audio_player.src = f_path
            audio_player.update()
            audio_player.play()
            
            # 模拟等待播放结束（实际可监听 on_state_changed）
            # 由于 edge-tts 的段落通常不长，我们这里用简单的逻辑
            await asyncio.sleep(2) # 演示逻辑，建议配合 on_state_changed
            
            if state["is_playing"] and state["session_id"] == current_session:
                state["idx"] += 1

    async def background_cache():
        sess = state["session_id"]
        while state["is_playing"] and state["session_id"] == sess:
            for i in range(CACHE_AHEAD):
                t_idx = state["idx"] + i
                if t_idx >= book["total"]: break
                f_path = os.path.join(SAVE_DIR, f"tts_{t_idx}_{sess}.mp3")
                if not os.path.exists(f_path):
                    await synthesize(book["paragraphs"][t_idx], f_path, state["speed_rate"], state["voice"])
            await asyncio.sleep(1)

    def handle_play(e):
        if not book["path"]: return
        state["is_playing"] = not state["is_playing"]
        play_btn.icon = ft.Icons.PAUSE_CIRCLE_FILLED if state["is_playing"] else ft.Icons.PLAY_CIRCLE_FILL
        if state["is_playing"]:
            state["session_id"] = int(time.time() * 1000)
            page.run_task(background_cache)
            page.run_task(play_loop)
        else:
            audio_player.pause()
        page.update()

    play_btn.on_click = handle_play

    # 文件选择
    def on_result(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                path = e.files[0].path
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.readlines()
                book["paragraphs"] = [l.strip() for l in content if l.strip()]
                book["total"] = len(book["paragraphs"])
                book["path"] = path
                state["idx"] = 0
                update_ui()
            except Exception as ex:
                status_text.value = f"读取失败: {str(ex)}"
                page.update()

    file_picker = ft.FilePicker(on_result=on_result)
    page.overlay.append(file_picker)

    # 布局
    page.appbar = ft.AppBar(
        title=ft.Text("晓依听书"),
        actions=[
            ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: file_picker.pick_files(allowed_extensions=["txt"])),
            loading_ring
        ]
    )

    page.add(
        ft.Container(
            content=ft.Column(ui_lines, alignment=ft.MainAxisAlignment.CENTER, spacing=20),
            expand=True
        ),
        ft.Divider(),
        ft.Row([status_text], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([play_btn], alignment=ft.MainAxisAlignment.CENTER),
        ft.Container(height=20)
    )

    # 启动后异步清理旧缓存，增加 try-except 容错防止崩溃
    async def clean_old_cache():
        await asyncio.sleep(2)
        if not os.path.exists(SAVE_DIR):
            return
        try:
            for f in os.listdir(SAVE_DIR):
                if f.endswith(".mp3") or f.endswith(".tmp"):
                    try: 
                        os.remove(os.path.join(SAVE_DIR, f))
                    except: 
                        pass
        except Exception:
            pass # 屏蔽由于没有读写权限引发的异常崩溃
    
    page.run_task(clean_old_cache)

if __name__ == "__main__":
    # 注意：不要在 ft.app 之外做复杂的 OS 操作
    ft.app(target=main)

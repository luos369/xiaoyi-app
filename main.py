import flet as ft
import flet_audio as fta
import asyncio
import edge_tts
import os
import time
import tempfile

# 手机系统安全目录
TMP_DIR = tempfile.gettempdir()

async def main(page: ft.Page):
    page.title = "晓依听书-Final"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
    state = {"lines": [], "idx": 0, "playing": False, "sid": 0}

    # UI 组件预设
    display = ft.Text("正在初始化...", size=20, weight="bold", text_align="center")
    info = ft.Text("", size=12)
    btn = ft.FloatingActionButton(icon=ft.Icons.PLAY_ARROW, disabled=True)
    
    # 🌟 延迟加载音频组件
    audio = None
    finish_signal = asyncio.Event()

    async def init_audio():
        nonlocal audio
        try:
            # 只有当用户点开软件后，再动态挂载音频
            audio = fta.Audio(autoplay=False)
            page.overlay.append(audio)
            audio.on_state_changed = lambda e: finish_signal.set() if e.data == "completed" else None
            display.value = "系统已就绪\n请导入小说文件"
            btn.disabled = False
            page.update()
        except Exception as e:
            display.value = f"硬件模块挂载失败\n{str(e)}"
            page.update()

    async def play_engine():
        curr_sid = state["sid"]
        while state["playing"] and state["idx"] < len(state["lines"]) and state["sid"] == curr_sid:
            display.value = state["lines"][state["idx"]]
            info.value = f"进度: {state['idx']+1} / {len(state['lines'])}"
            page.update()
            
            f_path = os.path.join(TMP_DIR, f"s_{curr_sid}.mp3")
            try:
                comm = edge_tts.Communicate(state["lines"][state["idx"]], "zh-CN-XiaoyiNeural")
                await comm.save(f_path)
            except: pass
            
            if os.path.exists(f_path) and audio:
                finish_signal.clear()
                audio.src = f_path
                page.update()
                audio.play()
                while not finish_signal.is_set() and state["playing"] and state["sid"] == curr_sid:
                    await asyncio.sleep(0.1)
            
            if state["playing"] and state["sid"] == curr_sid:
                state["idx"] += 1
        
        btn.icon = ft.Icons.PLAY_ARROW
        state["playing"] = False
        page.update()

    async def toggle_play(e):
        if not state["lines"]: return
        if state["playing"]:
            state["playing"] = False
            state["sid"] = int(time.time())
            if audio: audio.pause()
            btn.icon = ft.Icons.PLAY_ARROW
        else:
            state["playing"] = True
            state["sid"] = int(time.time())
            btn.icon = ft.Icons.PAUSE
            page.run_task(play_engine)
        page.update()

    async def pick_file(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                with open(e.files[0].path, 'r', encoding='utf-8') as f:
                    content = f.readlines()
            except:
                with open(e.files[0].path, 'r', encoding='gbk', errors='ignore') as f:
                    content = f.readlines()
            state["lines"] = [l.strip() for l in content if len(l.strip()) > 1]
            state["idx"] = 0
            display.value = "文件已导入，点击播放"
            page.update()

    picker = ft.FilePicker(on_result=pick_file)
    page.overlay.append(picker)
    btn.on_click = toggle_play

    page.add(
        ft.AppBar(title=ft.Text("晓依听书 v1.6"), bgcolor=ft.Colors.BLUE_50),
        ft.Container(display, padding=40, expand=True, alignment=ft.alignment.center),
        ft.Row([info], alignment="center"),
        ft.Row([
            ft.ElevatedButton("选择小说", icon=ft.Icons.UPLOAD_FILE, on_click=lambda _: picker.pick_files(allowed_extensions=["txt"])),
            btn
        ], alignment="center", spacing=20),
        ft.Container(height=40)
    )

    # 启动后稍微等 0.5 秒再加载硬件，给安卓 16 反应时间
    await asyncio.sleep(0.5)
    await init_audio()

ft.app(target=main)

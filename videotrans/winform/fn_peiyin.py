import json
import json
import os
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtCore import QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QFileDialog

from videotrans import translator, tts
from videotrans.configure import config
from videotrans.task._dubbing import DubbingSrt
from videotrans.tts import EDGE_TTS, AZURE_TTS, AI302_TTS, OPENAI_TTS, GPTSOVITS_TTS, COSYVOICE_TTS, FISHTTS, CHATTTS, \
    GOOGLE_TTS, ELEVENLABS_TTS, CLONE_VOICE_TTS, TTS_API, is_input_api, is_allow_lang
from videotrans.util import tools


class SignThread(QThread):
    uito = Signal(str)

    def __init__(self, uuid_list=None, parent=None):
        super().__init__(parent=parent)
        self.uuid_list = uuid_list

    def post(self, jsondata):

        self.uito.emit(json.dumps(jsondata))

    def run(self):
        length = len(self.uuid_list)
        while 1:
            if len(self.uuid_list) == 0 or config.exit_soft:
                self.post({"type": "end"})
                time.sleep(1)
                return

            for uuid in self.uuid_list:
                if uuid in config.stoped_uuid_set:
                    try:
                        self.uuid_list.remove(uuid)
                    except:
                        pass
                    continue
                q = config.uuid_logs_queue.get(uuid)
                if not q:
                    continue
                try:
                    if q.empty():
                        time.sleep(0.5)
                        continue
                    data = q.get(block=False)
                    if not data:
                        continue
                    self.post(data)
                    if data['type'] in ['error', 'succeed']:
                        self.uuid_list.remove(uuid)
                        self.post({"type": "jindu", "text": f'{int((length - len(self.uuid_list)) * 100 / length)}%'})
                        config.stoped_uuid_set.add(uuid)
                        del config.uuid_logs_queue[uuid]
                except:
                    pass


# 合成配音
def openwin():
    RESULT_DIR = config.HOME_DIR + "/tts"
    Path(RESULT_DIR).mkdir(exist_ok=True)

    def feed(d):
        if winobj.has_done:
            return
        if isinstance(d, str):
            d = json.loads(d)
        if d['type'] == 'replace':
            winobj.hecheng_plaintext.clear()
            winobj.hecheng_plaintext.insertPlainText(d['text'])
        elif d['type'] == 'error':
            winobj.has_done = True
            winobj.loglabel.setText(d['text'])
        elif d['type'] in ['logs', 'succeed']:
            if d['text']:
                winobj.loglabel.setText(d['text'])
        elif d['type'] == 'jindu':
            winobj.hecheng_startbtn.setText(d['text'])
        elif d['type'] == 'end':
            winobj.has_done = True
            winobj.hecheng_files = []
            winobj.hecheng_importbtn.setText(config.box_lang['Import text to be translated from a file..'])
            winobj.loglabel.setText(config.transobj['quanbuend'])
            winobj.hecheng_startbtn.setText(config.transobj["zhixingwc"])
            winobj.hecheng_startbtn.setDisabled(False)

    # 试听配音
    def listen_voice_fun():
        lang = translator.get_code(show_text=winobj.hecheng_language.currentText())
        if not lang or lang == '-':
            return QMessageBox.critical(winobj, config.transobj['anerror'],
                                        "选择字幕语言" if config.defaulelang == 'zh' else 'Please target language')
        text = config.params[f'listen_text_{lang}']
        role = winobj.hecheng_role.currentText()
        if not role or role == 'No':
            return QMessageBox.critical(winobj, config.transobj['anerror'], config.transobj['mustberole'])
        voice_dir = os.environ.get('APPDATA') or os.environ.get('appdata')
        if not voice_dir or not Path(voice_dir).exists():
            voice_dir = config.TEMP_DIR + "/voice_tmp"
        else:
            voice_dir = Path(voice_dir + "/pyvideotrans").as_posix()
        Path(voice_dir).mkdir(parents=True, exist_ok=True)
        lujing_role = role.replace('/', '-')

        rate = int(winobj.hecheng_rate.value())
        tts_type = winobj.tts_type.currentIndex()

        if rate >= 0:
            rate = f"+{rate}%"
        else:
            rate = f"{rate}%"
        volume = int(winobj.volume_rate.value())
        volume = f'+{volume}%' if volume >= 0 else f'{volume}%'
        pitch = int(winobj.pitch_rate.value())
        pitch = f'+{pitch}Hz' if pitch >= 0 else f'{volume}Hz'

        voice_file = f"{voice_dir}/{tts_type}-{lang}-{lujing_role}-{volume}-{pitch}.mp3"

        obj = {
            "text": text,
            "rate": rate,
            "role": role,
            "filename": voice_file,
            "tts_type": tts_type,
            "language": lang,
            "volume": volume,
            "pitch": pitch,
        }

        if role == 'clone':
            return

        threading.Thread(target=tts.run, kwargs={"queue_tts": [obj], "play": True, "is_test": True}).start()

    def change_by_lang(type):
        if type in [EDGE_TTS, AZURE_TTS]:
            return True
        if type == AI302_TTS and config.params['ai302tts_model'] == 'azure':
            return True
        if type == AI302_TTS and config.params['ai302tts_model'] == 'doubao':
            return True
        return False

    # tab-4 语音合成
    def hecheng_start_fun():
        winobj.has_done = False
        config.settings = config.parse_init()
        txt = winobj.hecheng_plaintext.toPlainText().strip()
        language = winobj.hecheng_language.currentText()
        role = winobj.hecheng_role.currentText()
        rate = int(winobj.hecheng_rate.value())
        tts_type = winobj.tts_type.currentIndex()
        langcode = translator.get_code(show_text=language)

        if language == '-' or role == 'No':
            return QMessageBox.critical(winobj, config.transobj['anerror'],
                                        config.transobj['yuyanjuesebixuan'])
        if is_input_api(tts_type=tts_type) is not True:
            return False

        # 语言是否支持
        is_allow_lang_res = is_allow_lang(langcode=langcode, tts_type=tts_type)
        if is_allow_lang_res is not True:
            return QMessageBox.critical(winobj, config.transobj['anerror'], is_allow_lang_res)

        if rate >= 0:
            rate = f"+{rate}%"
        else:
            rate = f"{rate}%"
        volume = int(winobj.volume_rate.value())
        pitch = int(winobj.pitch_rate.value())
        volume = f'+{volume}%' if volume >= 0 else f'{volume}%'
        pitch = f'+{pitch}Hz' if pitch >= 0 else f'{volume}Hz'

        # 文件名称
        # filename = winobj.hecheng_out.text()
        # if os.path.exists(filename):
        #     filename = ''
        # if filename and re.search(r'[\\/]+', filename):
        #     filename = ""
        # if not filename:
        #     newrole = role.replace('/', '-').replace('\\', '-')
        #     filename = f"{newrole}-rate{rate}-volume{volume}-pitch{pitch}"
        #     filename = filename.replace('%', '').replace('+', '')

        if len(winobj.hecheng_files) < 1 and not txt:
            return QMessageBox.critical(winobj, config.transobj['anerror'],
                                        '必须导入srt文件或在文本框中填写文字' if config.defaulelang == 'zh' else 'Must import srt file or fill in text box with text')
        elif len(winobj.hecheng_files) < 1:
            newsrtfile = config.TEMP_HOME + f"/peiyin{time.time()}.srt"
            tools.save_srt(tools.get_subtitle_from_srt(txt, is_file=False), newsrtfile)
            winobj.hecheng_files.append(newsrtfile)

        config.box_tts = 'ing'
        video_list = [tools.format_video(it, None) for it in winobj.hecheng_files]
        uuid_list = [obj['uuid'] for obj in video_list]
        for it in video_list:
            trk = DubbingSrt({
                "voice_role": role,
                "cache_folder": config.TEMP_HOME + f'/{it["uuid"]}',
                "target_language_code": langcode,
                "target_dir": RESULT_DIR,
                "voice_rate": rate,
                "volume": volume,
                "inst": None,
                "uuid": it['uuid'],
                "task_type": "childwin",
                "pitch": pitch,
                "tts_type": tts_type,
                "out_ext": winobj.out_format.currentText(),
                "voice_autorate": winobj.voice_autorate.isChecked()
            }, it)
            config.dubb_queue.append(trk)

        th = SignThread(uuid_list=uuid_list, parent=winobj)
        th.uito.connect(feed)
        th.start()
        winobj.hecheng_startbtn.setText(config.transobj["running"])
        winobj.hecheng_startbtn.setDisabled(True)

    # tts类型改变
    def tts_type_change(type):
        if change_by_lang(type):
            winobj.volume_rate.setDisabled(False)
            winobj.pitch_rate.setDisabled(False)
        else:
            winobj.volume_rate.setDisabled(True)
            winobj.pitch_rate.setDisabled(True)

        code = translator.get_code(show_text=winobj.hecheng_language.currentText())

        is_allow_lang_res = is_allow_lang(langcode=code, tts_type=type)
        if is_allow_lang_res is not True:
            return QMessageBox.critical(winobj, config.transobj['anerror'], is_allow_lang_res)
        if is_input_api(tts_type=type) is not True:
            return False

        if type == GOOGLE_TTS:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(['gtts'])
        elif type == CHATTTS:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(['No'] + list(config.ChatTTS_voicelist))
        elif type == OPENAI_TTS:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(config.params['openaitts_role'].split(","))
        elif type == ELEVENLABS_TTS:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(config.params['elevenlabstts_role'])
        elif change_by_lang(type):
            hecheng_language_fun(winobj.hecheng_language.currentText())
        elif type == AI302_TTS:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(config.params['ai302tts_role'].split(","))
        elif type == CLONE_VOICE_TTS:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems([it for it in config.params["clone_voicelist"] if it != 'clone'])
        elif type == TTS_API:
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(config.params['ttsapi_voice_role'].split(","))
        elif type == GPTSOVITS_TTS:
            rolelist = tools.get_gptsovits_role()
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(list(rolelist.keys()) if rolelist else ['GPT-SoVITS'])
        elif type == COSYVOICE_TTS:
            rolelist = tools.get_cosyvoice_role()
            del rolelist["clone"]
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(list(rolelist.keys()) if rolelist else ['-'])
        elif type == FISHTTS:
            rolelist = tools.get_fishtts_role()
            winobj.hecheng_role.clear()
            winobj.hecheng_role.addItems(list(rolelist.keys()) if rolelist else ['FishTTS'])

    # 合成语言变化，需要获取到角色
    def hecheng_language_fun(t):
        code = translator.get_code(show_text=t)
        tts_type = winobj.tts_type.currentIndex()
        if code and code != '-':
            is_allow_lang_reg = is_allow_lang(langcode=code, tts_type=tts_type)
            if is_allow_lang_reg is not True:
                return QMessageBox.critical(winobj, config.transobj['anerror'], is_allow_lang_reg)
        # 不是跟随语言变化的配音渠道，无需继续处理
        if not change_by_lang(tts_type):
            return
        winobj.hecheng_role.clear()
        if t == '-':
            winobj.hecheng_role.addItems(['No'])
            return

        if tts_type == EDGE_TTS:
            show_rolelist = tools.get_edge_rolelist()
        elif tts_type == AI302_TTS and config.params['ai302tts_model'] == 'doubao':
            show_rolelist = tools.get_302ai_doubao()
        else:
            # AzureTTS或 302.ai选择doubao模型
            show_rolelist = tools.get_azure_rolelist()
        if not show_rolelist:
            winobj.hecheng_language.setCurrentText('-')
            QMessageBox.critical(winobj, config.transobj['anerror'], config.transobj['nojueselist'])
            return
        try:
            vt = code.split('-')[0]
            if vt not in show_rolelist:
                winobj.hecheng_role.addItems(['No'])
                return
            if len(show_rolelist[vt]) < 2:
                winobj.hecheng_language.setCurrentText('-')
                QMessageBox.critical(winobj, config.transobj['anerror'], config.transobj['waitrole'])
                return
            winobj.hecheng_role.addItems(show_rolelist[vt])
        except:
            winobj.hecheng_role.addItems(['No'])

    # 导入字幕
    def hecheng_import_fun():
        fnames, _ = QFileDialog.getOpenFileNames(winobj, "Select srt", config.params['last_opendir'],
                                                 "Text files(*.srt *.txt)")
        if len(fnames) < 1:
            return
        namestr = []
        for (i, it) in enumerate(fnames):
            it = it.replace('\\', '/').replace('file:///', '')
            if it.endswith('.txt'):
                shutil.copy2(it, f'{it}.srt')
                # 使用 "r+" 模式打开文件：读取和写入
                with open(f'{it}.srt', 'r+', encoding='utf-8') as file:
                    # 读取原始文件内容
                    original_content = file.readlines()
                    # 将文件指针移动到文件开始位置
                    file.seek(0)
                    # 将新行内容与原始内容合并，并写入文件
                    file.writelines(["1\n", "00:00:00,000 --> 00:05:00,000\n"] + original_content)

                it += '.srt'
            fnames[i] = it
            namestr.append(os.path.basename(it))

        if len(fnames) > 0:
            config.params['last_opendir'] = os.path.dirname(fnames[0])
            winobj.hecheng_files = fnames
            winobj.hecheng_importbtn.setText(
                f'导入{len(fnames)}个srt文件 \n{",".join(namestr)}' if config.defaulelang == 'zh' else f'Import {len(fnames)} Subtitles \n{",".join(namestr)}')

    def opendir_fn():
        QDesktopServices.openUrl(QUrl.fromLocalFile(RESULT_DIR))

    from videotrans.component import Peiyinform
    try:
        winobj = config.child_forms.get('peiyinform')
        if winobj is not None:
            winobj.show()
            winobj.raise_()
            winobj.activateWindow()
            return
        winobj = Peiyinform()
        config.child_forms['peiyinform'] = winobj
        winobj.hecheng_importbtn.clicked.connect(hecheng_import_fun)
        winobj.hecheng_language.currentTextChanged.connect(hecheng_language_fun)
        winobj.hecheng_startbtn.clicked.connect(hecheng_start_fun)
        winobj.listen_btn.clicked.connect(listen_voice_fun)
        winobj.hecheng_opendir.clicked.connect(opendir_fn)
        winobj.tts_type.currentIndexChanged.connect(tts_type_change)

        winobj.show()
    except Exception as e:
        import traceback
        traceback.print_exc()
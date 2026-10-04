import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from converter_i18n import Translator, game_labels, Message, diagnostic_payload, restore_diagnostic
from converter_output_language import verify, write_guide, output_language


def localization(base, language, text, replace=False):
    path=base/'localization'/('replace' if replace else '')/language/('fixture_l_'+language+'.yml')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('l_'+language+':\n'+text,encoding='utf-8-sig')
    return path


class TranslationTests(unittest.TestCase):
    def test_backend_messages_preserve_original_reports_and_user_text(self):
        from copy import deepcopy
        from converter_edits import integer
        tr=Translator('en')
        path='D:/玩家/模组名称不能为空/{save}.eu5'
        value=Message('找不到模组目录：{0}',path)
        self.assertEqual(tr(value),'Mod directory not found: '+path)
        self.assertEqual(tr(deepcopy(value)),tr(value))
        self.assertEqual(json.loads(json.dumps({'reason':value},ensure_ascii=False)),{'reason':'找不到模组目录：'+path})
        self.assertEqual(Translator('zh-CN')(value),str(value))
        with self.assertRaises(ValueError) as raised:integer(-1,Message('建筑等级'),100)
        self.assertEqual(tr(raised.exception),'Building level must be an integer from 0 to 100')

    def test_worker_error_roundtrip_keeps_nested_translation_and_raw_arguments(self):
        tr=Translator('en');name='模组名称不能为空'
        reason=Message('发现多个匹配目录，无法确定使用哪一个')
        original=Message('存档需要模组 {0} {1}，但本机{2}。请在导入窗口添加正确的模组目录。',name,'1.2',reason)
        payload=json.loads(json.dumps(diagnostic_payload(ValueError(original)),ensure_ascii=False))
        restored=restore_diagnostic(payload,'original fallback')
        self.assertEqual(str(restored),str(original))
        self.assertIn(name,tr(restored))
        self.assertIn('multiple matching folders',tr(restored))
        self.assertEqual(restore_diagnostic({'source':'{3}','arguments':['one']},'original'),'original')
        self.assertIsNone(diagnostic_payload(ValueError('unrecognized raw diagnostic')))

    def test_conversion_worker_failure_reaches_ui_as_translatable_message(self):
        from types import SimpleNamespace
        from converter_pipeline import run_conversion
        from converter_project import write
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);save=base/'玩家存档.eu5';save.write_text('fixture',encoding='utf-8')
            reason=Message('找不到模组目录：{0}','D:/玩家/mod')
            def worker(command,**kwargs):
                run=Path(command[-1]).parent
                write(run/'status.json',{'error':str(reason),'error_message':diagnostic_payload(reason)})
                return SimpleNamespace(wait=lambda timeout:1)
            with patch('converter_pipeline.subprocess.Popen',side_effect=worker):
                with self.assertRaises(ValueError) as raised:
                    run_conversion(base,base/'workspace',dict(save=str(save),game=str(base),eu5=str(base),rules=str(save)))
            rendered=Translator('en')(raised.exception)
            self.assertIn('Mod directory not found: D:/玩家/mod',rendered)
            self.assertIn('; log:',rendered)
            self.assertIn('找不到模组目录',str(raised.exception))

    def test_backend_message_catalog_has_no_untranslated_templates(self):
        tr=Translator('en');missing=[]
        names=('converter_project','converter_world','converter_arable_advice','converter_supplement',
               'converter_food_markets','converter_edits','converter_reconcile','converter_controller',
               'converter_export','initialize_converter','converter_import','converter_pipeline')
        for name in names:
            tree=ast.parse(Path(__file__).with_name(name+'.py').read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Message' and isinstance(node.args[0],ast.Constant):
                    if node.args[0].value not in tr.messages:missing.append((name,node.args[0].value))
        self.assertEqual(missing,[])

    def test_export_preference_is_versioned_and_preserves_other_settings(self):
        from converter_controller import App
        from converter_project import read
        with tempfile.TemporaryDirectory() as td:
            app=App(td);app.project=dict(id='a'*32,revision=0,name='Test',settings={'sentinel':1},merges=[])
            result=app.configure_export_name('English campaign',0,'en')
            self.assertEqual(result['revision'],1)
            self.assertEqual(result['settings'],{'sentinel':1})
            self.assertEqual(read(Path(td)/'projects'/('a'*32)/'project.json')['output_language'],'en')
            self.assertEqual(app.configure_export_name('English campaign',1,'en')['revision'],1)
            with self.assertRaises(RuntimeError):app.configure_export_name('Stale',0,'zh-CN')
            with self.assertRaises(ValueError):app.configure_export_name('Invalid',1,'fr')
            self.assertEqual(app.project['output_language'],'en')

    def test_catalog_covers_desktop_messages_and_formats_arguments(self):
        tr=Translator('en-US')
        source=Path(__file__).with_name('converter_desktop.py').read_text(encoding='utf-8')
        tree=ast.parse(source)
        from converter_desktop import RISKS,LAYERS,FILTERS,PARAMS,STAGES
        required=set(RISKS.values())|set(LAYERS)|set(FILTERS)|set(STAGES.values())|{v[1] for v in PARAMS}|{'未知'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='tr' and node.args and isinstance(node.args[0],ast.Constant):
                required.add(node.args[0].value)
        self.assertFalse(required-set(tr.messages))
        self.assertEqual(tr('将 {0} 的{1}并入 {2}','A','region','B'),'Merge region of A into B')
        self.assertEqual(Translator('fr')('未知'),'未知')
        self.assertEqual(tr('user supplied name'),'user supplied name')

    def test_invalid_placeholder_is_rejected(self):
        with patch('converter_i18n.json.load',return_value={'hello {0}':'hello {1}'}):
            with self.assertRaisesRegex(ValueError,'placeholders'):Translator('en')

    def test_game_names_use_selected_language_with_mod_override_and_english_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            game,mod=Path(td)/'game',Path(td)/'mod'
            localization(game,'english',' A:0 "Base"\n B:0 "Fallback"\n')
            localization(game,'simp_chinese',' A:0 "原版"\n')
            localization(mod,'english',' A:0 "Mod"\n')
            localization(mod,'english',' A:0 "Replacement"\n',replace=True)
            localization(mod,'simp_chinese',' A:0 "模组"\n',replace=True)
            self.assertEqual(game_labels(game,mod,'en'),{'A':'Replacement','B':'Fallback'})
            self.assertEqual(game_labels(game,mod,'zh-CN'),{'A':'模组','B':'Fallback'})

    def test_output_requires_selected_language_without_silently_copying_chinese(self):
        with tempfile.TemporaryDirectory() as td:
            mod,game=Path(td)/'mod',Path(td)/'game'
            localization(mod,'simp_chinese',' A:0 "中文"\n LAST:0 ""\n')
            path=localization(mod,'english',' LAST:0 ""\n')
            original=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'Missing english localization: A'):verify(mod,game,'en')
            self.assertEqual(path.read_bytes(),original)
            localization(mod,'english',' A:0 "English"\n LAST:0 ""\n')
            result=verify(mod,game,'en')
            self.assertEqual(result['checked_keys'],2)
            self.assertFalse(result['runtime_verified'])
            write_guide(Path(td),'en')
            self.assertIn('not a .v3 save',(Path(td)/'README.txt').read_text(encoding='utf-8'))

    def test_output_validates_headers_bom_and_language(self):
        with tempfile.TemporaryDirectory() as td:
            mod=Path(td)/'mod';game=Path(td)/'game'
            path=localization(mod,'english',' A:0 "English"\n')
            path.write_text('l_simp_chinese:\n A:0 "English"\n',encoding='utf-8-sig')
            with self.assertRaisesRegex(ValueError,'header'):verify(mod,game,'en')
            path.write_text('l_english:\n A:0 "English"\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'BOM'):verify(mod,game,'en')
            with self.assertRaises(ValueError):output_language('../../english')
            with self.assertRaisesRegex(ValueError,'does not exist'):verify(mod/'missing',game,'en')


if __name__=='__main__':unittest.main()

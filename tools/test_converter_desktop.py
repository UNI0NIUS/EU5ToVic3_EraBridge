"""Native widget callbacks and import diagnostics; no browser involved."""
from pathlib import Path
import tempfile
import time
import threading
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from converter_project import write,DEFAULTS
from converter_import import source_mods,discover_mods,import_error
from converter_desktop import Workbench

class ImportTests(unittest.TestCase):
    def test_cancelled_conversion_stops_its_worker_and_marks_run(self):
        from converter_pipeline import run_conversion
        from converter_project import read
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);save=td/'save.eu5';save.write_text('test',encoding='utf8');rules=td/'rules.json';write(rules,{})
            cancel=threading.Event();cancel.set()
            with self.assertRaisesRegex(RuntimeError,'转换已停止'):
                run_conversion(td,td/'workspace',dict(save=str(save),game=str(td),eu5=str(td),rules=str(rules)),cancel=cancel)
            states=list((td/'workspace/runs').glob('*/status.json'));self.assertEqual(len(states),1)
            self.assertEqual(read(states[0])['status'],'cancelled')
    def test_exact_version_and_original_order(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);install=td/'common/EU5';save=td/'save.txt'
            save.write_text('metadata={ latest_mods_used={ "B"="2" "A"=1 } }',encoding='utf8')
            for name,version,folder in [('A','1','a'),('B','2','b'),('B','1','old')]:
                write(td/'workshop/content/3450310'/folder/'.metadata/metadata.json',dict(name=name,version=version))
            mods=discover_mods(source_mods(save),install)
            self.assertEqual([Path(p).name for p in mods],['b','a'])
            with self.assertRaisesRegex(ValueError,'没有找到'):discover_mods([('A','99')],install)
    def test_duplicate_match_requires_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            for folder in ['a','b']:write(td/'workshop/content/3450310'/folder/'.metadata/metadata.json',dict(name='A',version='1'))
            with self.assertRaisesRegex(ValueError,'多个匹配'):discover_mods([('A','1')],td/'common/EU5')
    def test_log_exposes_cause_not_only_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);(td/'log.txt').write_text('date [INFO] reading\ndate [ERROR] Missing mod metadata: X',encoding='utf8')
            self.assertEqual(import_error(td,-1),'Missing mod metadata: X')

class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.root.withdraw()
        with patch('converter_desktop.App.defaults',return_value=dict(candidates=[],projects=[],game='',eu5='')):
            self.ui=Workbench(self.root,Path(self.temp.name),autoload=False)
    def tearDown(self):
        self.ui.selection_pool.shutdown(wait=True,cancel_futures=True)
        try:self.root.destroy()
        except tk.TclError:pass
        self.temp.cleanup()
    def pump(self):
        deadline=time.monotonic()+5
        while self.ui.busy and time.monotonic()<deadline:self.root.update();time.sleep(.01)
        self.assertFalse(self.ui.busy)

    def test_language_switch_preserves_draft_and_stable_control_ids(self):
        self.ui.params['population_multiplier'].set('1.25')
        self.ui.layer.set('市场归属');self.ui.filter.set('严重失业');self.ui.kind.set('当前州内的地区')
        self.ui.save_preferences(last_project='remember-me')
        self.ui.language_choice.set('English');self.ui.change_language()
        self.assertEqual(self.ui.params['population_multiplier'].get(),'1.25')
        self.assertEqual(self.ui.layers[self.ui.layer.get()],'market')
        self.assertEqual(self.ui.filters[self.ui.filter.get()],'unemployment')
        self.assertEqual(self.ui.kind.get(),'Region within this state')
        self.assertEqual(self.ui.fmt(None),'Unknown')
        from converter_project import read
        self.assertEqual(read(self.ui.preferences),dict(language='en',last_project='remember-me'))
        self.ui.language_choice.set('简体中文');self.ui.change_language()
        self.assertEqual(self.ui.kind.get(),'当前州内的地区')
        self.assertEqual(self.ui.params['population_multiplier'].get(),'1.25')

    def test_language_does_not_change_during_background_operation(self):
        self.ui.busy=True;self.ui.language_choice.set('English');self.ui.change_language()
        self.assertEqual(self.ui.translator.language,'zh-CN')
        self.assertEqual(self.ui.language_choice.get(),'简体中文')
        self.ui.busy=False

    def test_english_backend_error_translates_display_but_preserves_log(self):
        from converter_project import settings
        self.ui.language_choice.set('English');self.ui.change_language()
        with patch('converter_desktop.messagebox.showerror') as error:
            self.ui.submit('Check settings',lambda:settings({'population_multiplier':99}))
            self.pump()
        self.assertIn('population_multiplier must be between 0.1 and 5',error.call_args.args[1])
        log=next((Path(self.temp.name)/'logs').glob('desktop-*.log')).read_text(encoding='utf-8')
        self.assertIn('必须在',log)

    def test_english_assumptions_translate_without_modifying_preview(self):
        from converter_i18n import Message
        original=Message('失业为岗位容量缺口估算；未模拟资质、工资、价格和实际招聘。')
        self.ui.language_choice.set('English');self.ui.change_language()
        self.ui.app.preview={'assumptions':[original]}
        with patch('converter_desktop.messagebox.showinfo') as info:self.ui.assumptions()
        self.assertIn('Unemployment estimates a job-capacity gap',info.call_args.args[1])
        self.assertIs(self.ui.app.preview['assumptions'][0],original)

    def test_english_action_buttons_fit_at_minimum_window_width(self):
        self.ui.language_choice.set('English');self.ui.change_language()
        self.root.attributes('-alpha',0);self.root.geometry('1080x760');self.root.deiconify();self.root.update()
        def descendants(parent):
            for child in parent.winfo_children():yield child;yield from descendants(child)
        clipped=[w.cget('text') for w in descendants(self.root)
                 if isinstance(w,ttk.Button) and w.winfo_width()+2<w.winfo_reqwidth()]
        self.assertEqual(clipped,[])
        self.root.withdraw()

    def test_construction_goal_is_correct_in_both_languages(self):
        from types import SimpleNamespace
        self.ui.app.project={'settings':DEFAULTS,'merges':[]}
        self.ui.app.world=SimpleNamespace(labels={},target=SimpleNamespace(buildings={'building_wheat_farm':{}}))
        sample_rows={'S|AAA':dict(state_name='State',country_name='Country',provinces=['x000001'],buildings={})}
        def descendants(parent):
            for child in parent.winfo_children():yield child;yield from descendants(child)
        for language in ('English','简体中文'):
            self.ui.rows={}
            self.ui.language_choice.set(language);self.ui.change_language()
            self.ui.rows=sample_rows
            for metric,label in [('food','市场接入后的食物缺口'),('unemployment','失业岗位缺口')]:
                with self.subTest(language=language,metric=metric),patch.object(self.ui,'submit',side_effect=lambda title,fn,done:fn()),patch('converter_supplement.proposal',return_value={}) as propose:
                    self.ui.supplement_dialog('x000001')
                    widgets=list(descendants(self.root))
                    box=next(w for w in widgets if isinstance(w,ttk.Combobox) and self.ui.tr(label) in w.cget('values'))
                    box.set(self.ui.tr(label))
                    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')==self.ui.tr('计算补建方案')).invoke()
                    self.assertEqual(propose.call_args.args[5],metric)

    def test_english_merge_uses_region_identifier_and_unmodified_tags(self):
        self.ui.language_choice.set('English');self.ui.change_language()
        self.ui.app.project={'id':'test'}
        self.ui.rows={'S|AAA':dict(state='S',country='AAA',country_name='Alpha',neighbors=[])}
        self.ui.selected='S|AAA';self.ui.targets={'Beta':'BBB'};self.ui.target.set('Beta')
        self.ui.kind.set('Region within this state')
        with patch.object(self.ui,'review_edit') as review:
            self.ui.merge()
        self.assertEqual(review.call_args.args[0],dict(kind='region',source='AAA',target='BBB',state='S'))

    def test_language_saved_on_restart_and_output_language_is_independent(self):
        from converter_project import write
        write(self.ui.preferences,dict(language='en',last_project='old'))
        other=tk.Toplevel(self.root)
        with patch('converter_desktop.App.defaults',return_value=dict(candidates=[],projects=[],game='',eu5='')):
            ui=Workbench(other,Path(self.temp.name),autoload=False)
        try:
            self.assertEqual(ui.translator.language,'en')
            d,f=ui.dialog('Test');get_language=ui.output_language_field(f,0,'zh-CN')
            self.assertEqual(get_language(),'zh-CN');d.destroy()
        finally:
            ui.selection_pool.shutdown(wait=True,cancel_futures=True);other.destroy()
    def test_background_error_reenables_controls_and_displays_cause(self):
        with patch('converter_desktop.messagebox.showerror') as error:
            self.ui.submit('测试导入',lambda:(_ for _ in ()).throw(ValueError('缺少所需模组')))
            self.pump();self.assertIn('缺少所需模组',error.call_args.args[1])
            self.assertTrue(all('disabled' not in b.state() for b in self.ui.mutators))
    def test_native_picker_is_parented_and_updates_path(self):
        frame=ttk.Frame(self.root);value=self.ui.path_field(frame,0,'EU5','',kind='save')
        button=next(w for w in frame.winfo_children() if isinstance(w,ttk.Button))
        with patch('converter_desktop.filedialog.askopenfilename',return_value='D:/世界.eu5') as picker:
            button.invoke();self.assertEqual(value.get(),'D:/世界.eu5');self.assertIs(picker.call_args.kwargs['parent'],self.root)
    def test_baseline_picker_accepts_v3_and_preserves_dialog_parent(self):
        frame=ttk.Frame(self.root);value=self.ui.path_field(frame,0,'基准','',kind='baseline')
        button=next(w for w in frame.winfo_children() if isinstance(w,ttk.Button))
        with patch('converter_desktop.filedialog.askopenfilename',return_value='D:/基准.v3') as picker:
            button.invoke()
            self.assertEqual(value.get(),'D:/基准.v3')
            self.assertIs(picker.call_args.kwargs['parent'],self.root)
            self.assertIn(('V3 开局存档','*.v3'),picker.call_args.kwargs['filetypes'])

    def test_cancelled_picker_preserves_value(self):
        frame=ttk.Frame(self.root);value=self.ui.path_field(frame,0,'目录','existing')
        button=next(w for w in frame.winfo_children() if isinstance(w,ttk.Button))
        with patch('converter_desktop.filedialog.askdirectory',return_value=''):
            button.invoke();self.assertEqual(value.get(),'existing')
    def test_parameters_percentages_are_converted(self):
        self.ui.params['unemployment_threshold'].set('30')
        with patch.object(self.ui,'mutate') as mutate:
            self.ui.apply();self.assertEqual(mutate.call_args.args[1]['settings']['unemployment_threshold'],.3)
    def test_idle_exit_destroys_window(self):
        with patch.object(self.root,'destroy') as destroy:self.ui.close();destroy.assert_called_once()
    def test_busy_exit_cancels_conversion_without_discarding_export(self):
        self.ui.busy=True;self.ui.operation='转换存档'
        with patch('converter_desktop.messagebox.askyesno',return_value=True):self.ui.close()
        self.assertTrue(self.ui.cancel.is_set());self.assertTrue(self.ui.closing)
        self.ui.cancel.clear();self.ui.operation='导出并校验模组'
        with patch('converter_desktop.messagebox.askyesno',return_value=True):self.ui.close()
        self.assertFalse(self.ui.cancel.is_set())

    def test_selection_during_recompute_keeps_latest_click_and_does_not_lock_ui(self):
        import base64,io
        from PIL import Image
        image=io.BytesIO();Image.new('RGBA',(1,1),(255,255,0,255)).save(image,format='PNG')
        result=dict(image='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode(),box=[0,0,1,1],xy=[0,0],focus=[0,0,1,1])
        self.ui.rows={'A':{},'B':{}};self.ui.app.preview={};started=threading.Event();release=threading.Event()
        def region(key,*args):
            if key=='A':started.set();release.wait(3)
            return dict(result,xy=[1 if key=='A' else 2,0])
        with patch.object(self.ui.app,'region',side_effect=region),patch.object(self.ui,'show_details'),patch.object(self.ui,'draw'):
            self.ui.busy=True;self.ui.select('A');self.assertTrue(started.wait(2))
            self.ui.select('B');self.assertEqual(self.ui.selected,'B');release.set()
            deadline=time.monotonic()+5
            while self.ui.selecting and time.monotonic()<deadline:self.root.update();time.sleep(.01)
            self.assertFalse(self.ui.selecting);self.assertEqual(self.ui.marker,[2,0])
            self.assertTrue(self.ui.busy)  # Selection must not clear an unrelated mutation job.
            self.ui.busy=False

    def test_invalid_target_click_exits_pick_mode_instead_of_trapping_map(self):
        self.ui.rows={'A':{'country':'AAA'}};self.ui.picking=True;self.ui.targets={}
        with patch.object(self.ui,'show_details'),patch.object(self.ui.app,'region',side_effect=ValueError('test')):
            self.ui.select('A')
            self.assertFalse(self.ui.picking);self.assertEqual(self.ui.selected,'A')

    def test_bulk_conflict_dialog_defaults_to_preserve_and_requires_demolition_choice(self):
        from types import SimpleNamespace
        from copy import deepcopy
        conflict=dict(state='S',source='AAA',target='BBB',building='factory',levels=7,reason='未解锁')
        op=dict(kind='bulk',transfers=[dict(state='S',source='AAA',target='BBB')])
        preview=dict(rows=[],adjustments=[],bulk_outcomes=[dict(applied=0,skipped=[conflict],conflicts=[conflict],demolitions=[])])
        automatic=deepcopy(preview);automatic['bulk_outcomes'][0].update(applied=1,skipped=[],demolitions=[conflict])
        self.ui.app.project=dict(settings=DEFAULTS,merges=[]);self.ui.app.preview=preview
        self.ui.app.world=SimpleNamespace(labels={'factory':'工厂'},preview=lambda options,ops:automatic if ops[-1].get('demolish') else preview)
        self.ui.review_edit(op,'test');self.pump()
        def widgets(parent):
            for w in parent.winfo_children():yield w;yield from widgets(w)
        controls=list(widgets(self.root));button=next(w for w in controls if isinstance(w,ttk.Button) and w.cget('text')=='确认应用')
        self.assertIn('disabled',button.state())
        text=next(w for w in controls if isinstance(w,tk.Text));self.assertIn('工厂 × 7',text.get('1.0','end'))
        next(w for w in controls if isinstance(w,ttk.Radiobutton) and str(w.cget('value'))=='1').invoke()
        self.assertNotIn('disabled',button.state());self.assertIn('将拆除',text.get('1.0','end'))
        with patch.object(self.ui,'mutate') as mutate:
            button.invoke();self.assertIs(mutate.call_args.args[1]['operation']['demolish'],True)

if __name__=='__main__':unittest.main()

"""Source identity and conditional heraldry regressions."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from m3_flags import FlagExporter, flag_design, resolve_constants
from pdx_text import root


class FlagsTests(unittest.TestCase):
    def test_constants_are_scoped_and_arithmetic_only(self):
        s=resolve_constants('@x = 2 A={ @x = @[1/4] p={ @x @[x*2] } } B={ p=@x }')
        self.assertIn('p={ 0.25 0.5 }',s)
        self.assertIn('p=2',s)
        self.assertIn('@[f()]',resolve_constants('A={ p=@[f()] }'))
        self.assertIn('@missing',resolve_constants('A={p=@missing}'))

    def test_unknown_conditions_are_not_assumed_true(self):
        f=FlagExporter.__new__(FlagExporter);f.triggers={}
        s={'government':'republic','reforms':[],'flag':'ITA','definition':'GEN'}
        self.assertTrue(f.trigger(root('OR={ unknown=yes has_or_had_tag=GEN }'),s,None))
        self.assertIsNone(f.trigger(root('NOT={ unknown=yes }'),s,None))
        self.assertFalse(f.trigger(root('government_type=government_type:monarchy'),s,None))
        self.assertIsNone(f.trigger(root('has_or_had_tag=VEN'),s,None))

    def test_missing_saved_flag_uses_tag_and_failed_import_is_transactional(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp)/'main_menu';d=b/'common/coat_of_arms/coat_of_arms';d.mkdir(parents=True)
            (d/'x.txt').write_text('BAD={pattern="ok.dds" sub={parent=MISSING}} NKD={}',encoding='utf-8')
            assets=b/'gfx/coat_of_arms/patterns';assets.mkdir(parents=True);(assets/'ok.dds').write_bytes(b'x')
            f=FlagExporter(Path(tmp));coa,key,attempts=f.resolve({'flag':'BAD','definition':'NKD'},'NKD')
            self.assertEqual(key,'NKD');self.assertEqual(len(attempts),1)
            self.assertFalse(f.assets);self.assertEqual(set(f.imported),{coa})

    def test_source_age_variant_has_priority_over_base(self):
        f=FlagExporter.__new__(FlagExporter);f.triggers={}
        f.flag_lists={'ITA':root('flag_definition={coa=old priority=1} flag_definition={coa=new priority=100 trigger={current_age=age_6_revolutions}} flag_definition={coa=unknown priority=999 trigger={unknown=yes}}')}
        self.assertEqual(f.candidates({'flag':'ITA'},'ITA','age_6_revolutions')[0],'new')
        self.assertEqual(f.candidates({'flag':'ITA'},'ITA')[0],'old')

    def test_native_tags_import_source_even_without_explicit_v3_flag_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            game=Path(tmp); d=game/'main_menu/common/coat_of_arms/coat_of_arms';d.mkdir(parents=True)
            (d/'x.txt').write_text('SRC={} OTHER_SOURCE={}',encoding='utf-8')
            defs=game/'common/flag_definitions';defs.mkdir(parents=True)
            (defs/'base.txt').write_text('AAA={flag_definition={coa=wrong}} KEEP={flag_definition={coa=preserve}}',encoding='utf-8')
            w=SimpleNamespace(game=game,country_defs={'AAA','BBB'},edges=[],profile={},
                countries={'AAA':{'source_id':'1','source_tag':'SRC','country_type':'recognized'},
                           'BBB':{'source_id':'2','source_tag':'OTHER_SOURCE','country_type':'recognized'}},
                politics={'countries':{'1':{'flag':'SRC'},'2':{'flag':'OTHER_SOURCE'}}},
                read=lambda rel:(game/rel).read_text(encoding='utf-8'))
            files={};out=SimpleNamespace(w=w,binary_assets={},write=lambda rel,text:files.update({rel:text}))
            FlagExporter(game).export(out)
            self.assertEqual([r['mode'] for r in out.flag_report],['imported_eu5_definition']*2)
            self.assertNotIn('wrong',files['common/flag_definitions/base.txt'])
            self.assertIn('coa=preserve',files['common/flag_definitions/base.txt'])
            self.assertIn('BBB',files['common/flag_definitions/zz_eu5_world.txt'])
            for rel in ('common/flag_definitions/base.txt','common/flag_definitions/zz_eu5_world.txt'):
                for tag,obj in root(files[rel]).fields().items():
                    if tag not in ('AAA','BBB'):continue
                    definition=obj.fields()['flag_definition'].fields()
                    self.assertEqual(definition['subject_canton'],definition['coa'])

    def test_colonial_family_color_and_all_layers_clear_canton(self):
        fields=set()
        for n in range(100):
            d=flag_design(str(n),[25,80,55],'catholic',True,'12_indonesia')
            fields.add(d['field']);self.assertEqual(len(d['positions']),1)
            self.assertIn(d['emblem'],('ce_palm_tree.dds','ce_ship_wheel.dds'))
            for layer in d['layers']:
                x,y=layer['position'];sx,sy=layer['scale']
                self.assertTrue(x-sx/2>=.4 or y-sy/2>=.4)
                self.assertLessEqual(x+sx/2,1);self.assertLessEqual(y+sy/2,1)
        self.assertEqual(len(fields),1)

if __name__=='__main__':unittest.main()

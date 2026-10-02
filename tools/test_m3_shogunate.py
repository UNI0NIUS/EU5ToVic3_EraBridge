import unittest
from copy import deepcopy
from m3_organizations import plan_blocs
from m3_shogunate import patch_rules,history
from pdx_text import root
from source_country_names import source_name_parts,opening_name,shogunate_roles
from m3_shogunate_runtime import charter_authority,export_runtime,EVENTS,JOURNAL,GLOBAL
from m3_shogunate_law import rewrite_country_history,assert_union_laws,law_body

class ShogunateTests(unittest.TestCase):
    def test_imported_bakufu_union_fix_works_for_arbitrary_tags(self):
        text='COUNTRIES={ c:AAA={activate_law=law_type:law_monarchy} c:ZZ9={activate_law=law_type:law_monarchy activate_law=law_type:law_bakufu} c:JAP={activate_law=law_type:law_bakufu} }'
        edges=[{'target_type':'personal_union','target_overlord':'AAA','target_subject':'ZZ9'}]
        with self.assertRaisesRegex(ValueError,'automatically breaks'):assert_union_laws(text,edges)
        fixed,tags=rewrite_country_history(text,{'AAA','ZZ9'})
        self.assertEqual(tags,['ZZ9']);self.assertEqual(assert_union_laws(fixed,edges),[['AAA','ZZ9']])
        self.assertIn('law_type:law_bakufu',root(fixed).fields()['COUNTRIES'].fields()['c:JAP'].text())
        self.assertEqual(rewrite_country_history(fixed,{'AAA','ZZ9'}),(fixed,[]))
    def test_republic_still_cannot_form_personal_union(self):
        text='COUNTRIES={ c:A={activate_law=law_type:law_monarchy} c:B={activate_law=law_type:law_presidential_republic} }'
        with self.assertRaisesRegex(ValueError,'needs a monarchy'):
            assert_union_laws(text,[{'target_type':'personal_union','target_overlord':'A','target_subject':'B'}])
    def test_economic_reader_resolves_variant_without_claiming_it_is_native(self):
        from economy_model import LawDefinitions
        defs=LawDefinitions({'law_bakufu':{'group':'lawgroup_distribution_of_power'}})
        self.assertEqual(defs['law_eu5_bakufu'],defs['law_bakufu'])
        self.assertNotIn('law_eu5_bakufu',defs)
        with self.assertRaises(KeyError):defs['law_unknown']
    def test_saved_territorial_name_precedes_historic_tag(self):
        src={'name':[['name','NKD'],['override_name','kamakura'],['override_adj','kamakura']], 'reforms':['daimyo']}
        self.assertEqual(source_name_parts(src,'NKD'),(None,'kamakura','kamakura'))
        self.assertEqual(opening_name(src,'镰仓','simp_chinese'),'镰仓藩')
        self.assertEqual(opening_name({'reforms':['shogunate']},'厚岸','simp_chinese'),'厚岸幕府')
    def test_regent_is_not_the_shogunate_office_holder(self):
        p={'countries':{'1':{'regent':'R','heir':'H'},'2':{'heir':'H'},'3':{'heir':'OTHER'}},'characters':{'H':{'dynasty':'satsuma_province'}}}
        roles=shogunate_roles(p,{'leader':'1','members':['1','2','3']})
        self.assertEqual(roles['shogun_character'],'H')
        self.assertEqual(roles['shogun_regent'],'R')
        self.assertEqual(roles['shared_heir_countries'],['1','2'])
    def test_unknown_policy_does_not_invent_authority_bonus(self):
        score,changes=charter_authority({'clan':'established_domains_policy','buke':'jap_buke_shohatto_guidelines','future':'unknown'})
        self.assertEqual(score,45);self.assertEqual(len(changes),2)
    def test_runtime_requires_consent_and_never_forces_historic_japan(self):
        from types import SimpleNamespace
        b=self.plan()['power_blocs'][0]
        countries={t:{'source_id':sid,'name_english':t,'name_simp_chinese':t} for sid,t in self.tags.items()}
        out=SimpleNamespace(outputs={},localization={'english':{},'simp_chinese':{}},
                            w=SimpleNamespace(countries=countries,politics={'countries':{'1':{}}}))
        out.write=lambda rel,text:out.outputs.__setitem__(rel,text)
        export_runtime(out,[b])
        events=out.outputs[EVENTS]
        self.assertIn('default_option = yes',events)
        self.assertIn('is_in_same_power_bloc = root',events)
        self.assertIn('annex = scope:eu5_petitioning_domain',events)
        self.assertNotIn('c:JAP',events);self.assertNotIn('change_tag',events)
        self.assertIn('is_power_bloc_leader = yes',out.outputs[JOURNAL])
        self.assertIn('eu5_shogunate_crisis_months value = 0',out.outputs[GLOBAL])
    def setUp(self):
        self.p={'date':'1780.7.4','international_organizations':[{'id':'5','type':'japanese_shogunate',
            'leader':'1','members':['1','2','3','4'],'special_statuses':{'japanese_emperor':['2']}}]}
        self.tags={'1':'SHO','2':'EMP','3':'REG','4':'DAI','5':'FOR'}
        self.cs={tag:{'country_type':'recognized'} for tag in self.tags.values()}
    def plan(self,edges=()):return plan_blocs(self.p,self.tags,self.cs,list(edges))
    def test_independent_shogun_leads(self):
        b=self.plan()['power_blocs'][0]
        self.assertEqual(b['leader'],'SHO');self.assertEqual(b['imperial_court'],['EMP'])
        self.assertEqual(b['principle'],'principle_eu5_shogunate_vassalization_1')
    def test_union_sovereign_leads_without_freeing_shogun_or_court(self):
        edges=[{'target_subject':'SHO','target_overlord':'REG'}, {'target_subject':'EMP','target_overlord':'REG'},
               {'target_subject':'DAI','target_overlord':'EMP'}]
        snapshot=deepcopy(edges);b=self.plan(edges)['power_blocs'][0]
        self.assertEqual(b['leader'],'REG');self.assertEqual(b['nominal_shogun'],'SHO')
        self.assertEqual(b['direct_members'],[]);self.assertEqual(b['members'],['DAI','EMP','REG','SHO'])
        self.assertEqual(edges,snapshot)
    def test_foreign_conqueror_is_not_invented_as_shogun(self):
        r=self.plan([{'target_subject':'SHO','target_overlord':'FOR'}])
        self.assertEqual(r['power_blocs'],[])
        self.assertEqual(r['omitted_organizations'][0]['reason'],'leader_is_subject')
    def test_vacuum_does_not_choose_strongest_daimyo(self):
        self.p['international_organizations'][0]['leader']='0'
        self.assertEqual(self.plan()['omitted_organizations'][0]['reason'],'source_leadership_vacuum')
    def test_rules_compose_with_hre_and_are_idempotent(self):
        old='can_lead_power_bloc={ OR={ country_rank >= rank_value:major_power eu5_is_chartered_hre_leader=yes }}\nis_weak_power_bloc={power_bloc_is_weak=yes NOT={has_identity=identity:identity_eu5_hre_empire}}'
        new=patch_rules(old)
        self.assertIn('eu5_is_chartered_hre_leader=yes',new)
        self.assertIn('identity:identity_eu5_hre_empire',new)
        self.assertEqual(patch_rules(new),new)
    def test_history_emits_optional_country_scope_and_only_direct_members(self):
        b=self.plan()['power_blocs'][0]
        cs=deepcopy(self.cs);cs['SHO']['source_id']='1'
        p={'countries':{'1':{'color':['10','20','30']}}}
        parsed=root(history([b],cs,p)).fields()['POWER_BLOCS'].fields()
        self.assertEqual(set(parsed),{'c:SHO'})
        init=parsed['c:SHO'].fields()['create_power_bloc']
        self.assertEqual([v for k,v in init.entries() if k=='member'],['c:DAI','c:EMP','c:REG'])

if __name__=='__main__':unittest.main()

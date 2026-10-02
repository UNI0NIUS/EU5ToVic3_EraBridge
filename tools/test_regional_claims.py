import unittest
from pdx_text import root
from regional_claims import plan,apply,bloc_leaders,japan_runtime,CODE,EFFECTS,HOOKS


class RegionalClaimsTests(unittest.TestCase):
    def setUp(self):
        self.policy={'version':'test','japan':{'states':['JAPAN','RYUKYU'],'reserved_tag':'JAP',
            'laws':['law_bakufu','law_eu5_bakufu'],'bloc_identity':'identity_eu5_shogunate'},
            'tibet':{'states':['LHASA','NGARI'],'native_culture':'tibetan','heritage':'heritage_tibetan'}}
        self.states='''STATES={s:JAPAN={create_state={country=c:SHG owned_provinces={a}}}
            s:RYUKYU={create_state={country=c:LEAD owned_provinces={b}} add_claim=c:OLD}
            s:LHASA={create_state={country=c:TIB owned_provinces={c}} create_state={country=c:TRB owned_provinces={d}}}
            s:NGARI={create_state={country=c:TIB owned_provinces={e}}}}'''
        self.history='COUNTRIES={c:SHG={activate_law=law_type:law_eu5_bakufu} c:LEAD={} c:TIB={}}'
        def definition(kind,cs):return {'country_type':kind,'cultures':root(cs)}
        self.defs={t:definition('unrecognized','japanese') for t in ['SHG','LEAD','JAP','OLD']}
        self.defs['TIB']=definition('unrecognized','eu5_khampa');self.defs['TRB']=definition('decentralized','tibetan')
        self.defs['DEAD']=definition('unrecognized','tibetan')
        self.cultures={'eu5_khampa':{'heritage':'heritage_tibetan'}}
    def make_plan(self):return plan(self.states,self.history,self.defs,self.cultures,{'LEAD'},self.policy)
    def test_arbitrary_tags_and_dormant_japan(self):
        report=self.make_plan();self.assertEqual(set(report['japan_eligible']),{'SHG','LEAD','JAP'})
        self.assertEqual(len([r for r in report['claims'] if r['rule']=='japan']),6)
    def test_white_land_gate_and_current_primary_culture(self):
        report=self.make_plan();self.assertEqual(set(report['tibet_eligible']),{'TIB'})
        self.assertEqual([(r['state'],r['tag']) for r in report['claims'] if r['rule']=='tibet'],[('LHASA','TIB')])
        self.assertEqual(report['skipped'][0]['state'],'NGARI')
    def test_no_white_no_tibetan_claims(self):
        self.defs['TRB']['country_type']='unrecognized'
        self.assertFalse([r for r in self.make_plan()['claims'] if r['rule']=='tibet'])
    def test_preserves_foreign_claim_and_is_idempotent(self):
        report=self.make_plan();new=apply(self.states,report)
        self.assertIn('add_claim=c:OLD',new)
        self.assertEqual(apply(new,report),new)
        self.assertEqual(new.count('owned_provinces'),self.states.count('owned_provinces'))
    def test_bloc_identity_not_every_bloc(self):
        text='POWER_BLOCS={c:ONE={create_power_bloc={identity=identity_eu5_shogunate}} c:TWO={create_power_bloc={identity=identity_eu5_hre_empire}}}'
        self.assertEqual(bloc_leaders([text],'identity_eu5_shogunate'),{'ONE'})
    def test_multicultural_primary_and_no_resident_population_inference(self):
        self.defs['LEAD']['cultures']=root('han tibetan')
        self.assertIn('LEAD',self.make_plan()['tibet_eligible'])
        self.defs['LEAD']['cultures']=root('han')
        self.assertNotIn('LEAD',self.make_plan()['tibet_eligible'])
    def test_japan_hooks_preserve_existing_and_are_idempotent(self):
        code='on_game_started={effect={native=yes} on_actions={old_hook}} on_country_formed={effect={native_formation=yes}} on_monthly_pulse_country={on_actions={native_monthly}} unrelated={effect={keep=yes}}'
        result=japan_runtime(code,self.policy)
        self.assertEqual(japan_runtime(result[CODE],self.policy),result)
        for token in ['native=yes','old_hook','native_formation=yes','native_monthly','unrelated={effect={keep=yes}}']:
            self.assertIn(token,result[CODE])
        self.assertIn('NOT = { has_variable = eu5_japan_claims_initialized }',result[EFFECTS])
        self.assertIn('c:JAP ?= THIS',result[HOOKS])
    def test_unknown_state_fails_instead_of_silent_omission(self):
        self.policy['japan']['states'].append('MISSING')
        with self.assertRaisesRegex(ValueError,'Unknown protected state'):self.make_plan()


if __name__=='__main__':unittest.main()

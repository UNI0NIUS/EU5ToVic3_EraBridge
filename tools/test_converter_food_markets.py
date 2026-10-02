from copy import deepcopy
from types import SimpleNamespace
import unittest
from pdx_text import root
from converter_food_markets import market_membership,allocate_food,transport_access

class MarketTests(unittest.TestCase):
    def setUp(self):
        self.actions={'vassal':{'pact':root('subject_type=subject_type_vassal')},'grant_own_market':{'pact':root('market_owner=second_country')}}
        self.identities={'trade':{'power_bloc_modifier':root('power_bloc_customs_union_bool=yes')},'religious':{}}
        self.principles={'unification_1':{},'unification_2':{'power_bloc_modifier':root('power_bloc_customs_union_bool=yes')}}
    def membership(self,diplomacy='',blocs=''):
        return market_membership({'AAA','BBB','CCC'},[diplomacy],[blocs],self.actions,self.identities,self.principles)[0]
    def test_subject_chain_joins_market_but_independence_splits_it(self):
        d='DIPLOMACY={c:AAA={create_diplomatic_pact={country=c:BBB type=vassal}} c:BBB={create_diplomatic_pact={country=c:CCC type=vassal}}}'
        self.assertEqual(self.membership(d),{'AAA':'AAA','BBB':'AAA','CCC':'AAA'})
        independent='DIPLOMACY={c:AAA={create_diplomatic_pact={country=c:BBB type=grant_own_market}}}'
        self.assertEqual(self.membership(d+independent),{'AAA':'AAA','BBB':'BBB','CCC':'BBB'})
    def test_power_bloc_membership_alone_does_not_imply_common_market(self):
        bloc='POWER_BLOCS={c:AAA={create_power_bloc={name=bloc identity=religious principle=unification_1 member=c:BBB}}}'
        self.assertEqual(self.membership(blocs=bloc)['BBB'],'BBB')
        self.assertEqual(self.membership(blocs=bloc.replace('religious','trade'))['BBB'],'AAA')
        self.assertEqual(self.membership(blocs=bloc.replace('unification_1','unification_2'))['BBB'],'AAA')
    def test_principle_added_to_existing_bloc_is_counted(self):
        bloc='POWER_BLOCS={c:AAA={create_power_bloc={name=bloc identity=religious member=c:BBB} power_bloc={add_principle=unification_2}}}'
        self.assertEqual(self.membership(blocs=bloc)['BBB'],'AAA')
    def test_bloc_respects_granted_market_independence(self):
        d='DIPLOMACY={c:AAA={create_diplomatic_pact={country=c:BBB type=grant_own_market}}}'
        bloc='POWER_BLOCS={c:AAA={create_power_bloc={name=bloc identity=trade member=c:BBB member=c:CCC}}}'
        self.assertEqual(self.membership(d,bloc),{'AAA':'AAA','BBB':'BBB','CCC':'AAA'})
    def rows(self):
        return [dict(state='S',country='AAA',food_supply=200,food_net={'grain':200},food_demand=100,food_shortfall=0,risks=[],population=1000,provinces=['x000001']),
                dict(state='T',country='BBB',food_supply=0,food_net={'grain':0},food_demand=100,food_shortfall=1,risks=['food','unemployment'],population=1000,provinces=['x000002'])]
    def test_food_surplus_is_shared_once_and_local_deficit_stays_visible(self):
        rows=self.rows();access={('S','AAA'):dict(ratio=1,connected=True),('T','BBB'):dict(ratio=1,connected=True)}
        pools=allocate_food(rows,{'AAA':'AAA','BBB':'AAA'},access,.2)
        self.assertEqual(rows[1]['food_shortfall'],0);self.assertEqual(rows[1]['local_food_shortfall'],1)
        self.assertEqual(rows[1]['risks'],['unemployment'])
        self.assertEqual(pools['AAA']['supply'],200)
    def test_isolated_or_unknown_region_is_not_falsely_cured(self):
        rows=self.rows();access={('S','AAA'):dict(ratio=1,connected=True),('T','BBB'):dict(ratio=0,connected=False)}
        allocate_food(rows,{'AAA':'AAA','BBB':'AAA'},access,.2)
        self.assertEqual(rows[1]['food_shortfall'],1)
        rows=self.rows();access['T','BBB']['ratio']=None
        allocate_food(rows,{'AAA':'AAA','BBB':'AAA'},access,.2)
        self.assertIsNone(rows[1]['food_shortfall']);self.assertNotIn('food',rows[1]['risks'])
    def test_industrial_food_inputs_offset_market_supply(self):
        rows=self.rows();rows[1]['food_net']={'grain':-100}
        access={('S','AAA'):dict(ratio=1,connected=True),('T','BBB'):dict(ratio=1,connected=True)}
        pools=allocate_food(rows,{'AAA':'AAA','BBB':'AAA'},access,.2)
        self.assertEqual(pools['AAA']['supply'],100)
        self.assertEqual(rows[1]['food_shortfall'],.5)
    def test_market_transport_needs_land_or_ports_at_both_ends(self):
        target=SimpleNamespace(infrastructure=lambda *a:100,infrastructure_usage=lambda *a:1)
        rows=self.rows();markets={'AAA':'AAA','BBB':'AAA'};techs={'AAA':set(),'BBB':set()}
        b=dict(building='building_port',state='T',owner='BBB',levels=1,pms=['pm_basic_port'])
        access=transport_access(rows,markets,{'AAA':'S'},[],{'x000001','x000002'},[b],target,techs)
        self.assertEqual(access['T','BBB']['ratio'],0)
        access=transport_access(rows,markets,{'AAA':'S'},[],{'x000001','x000002'},[b,dict(b,state='S',owner='AAA')],target,techs)
        self.assertEqual(access['T','BBB']['ratio'],1)
        access=transport_access(rows,markets,{'AAA':'S'},[('x000001','x000002')],set(),[],target,techs)
        self.assertEqual(access['T','BBB']['ratio'],1)

if __name__=='__main__':unittest.main()

"""Explicit lookup terms for linguistic review, not fuzzy production matching."""
import csv
import re
import unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'.local/m5/culture1337-research'

def norm(s):
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())

# A correspondence identifies the relevant catalog entry, NOT proof that its
# modern distribution or endonym applied in 1337. Explicit ambiguities stay out.
QUERIES='''
kangri|Kangri
polabian|Polabian
potiguara_culture|Tupinamba
griko_culture|Griko (Apulian Greek)
halbi|Halbi
sudovian|Sudovian
italki|Judeo-Italian
monkox_culture|Chiquitano
ayoreo_culture|Ayoreo
taino_culture|Taino
vepsian|Veps
muzo_culture|Muzo
sumbawa_culture|Sumbawa
napuruna_culture|Napo Lowland Quechua
danu_culture|Danu
achomi_culture|Lari
wapaji_culture|Wayampi
guenoa_culture|Guenoa
romanyoti|Judeo-Greek
ormur_culture|Ormuri
kambiwa_culture|Kambiwa
vedda|Veddah
kodaga|Kodava
ette_ennaka_culture|Chimila
guaikuru_culture|Guaicuruan
pume_culture|Pume
moqoit_culture|Mocovi
beary|Beary
mandean_culture|Classical Mandaic
cueva_culture|Cueva
ache_culture|Ache
kunama_culture|Kunama
southern_gallo_italic|Sicilian Galloitalian
hadiya_culture|Hadiyya
kadu_culture|Kadugli-Krongo
nivacle_culture|Nivacle
kuiba_culture|Cuiba
yugur_culture|West Yugur;East Yugur
wichi_culture|Wichi
surma_culture|Surmic
manggarai_culture|Manggarai
charrua_culture|Charrua
tabajara_culture|Tupinakin-Tupi-Tabajara Angra dos Reis-Cananéia
lio_culture|Lio
burusho|Burushaski
henia_culture|Comechingon
pasto_culture|Pasto
kambaata_culture|Kambaata
maleku_culture|Guatuso
gutnish|Archaic Gutnish
sarta_culture|Dongxiang
makas_culture|Maka
tatuy_culture|Timote-Cuica
enlhet_culture|Enlhet Norte
jasz_culture|Alanic
ingrian|Ingrian
juang_culture|Juang
dhofari_culture|Dhofari Arabic
baka_culture|Baka (Cameroon)
yshyr_culture|Chamacoco
danzhou_culture|Danzhou
tremembe_culture|Tremembe
warao_culture|Warao
venda_culture|Venda
pech_culture|Pech
ayamanes_culture|Ayaman
abipones_culture|Abipon
shuar_culture|Shuar
gyele_culture|Gyele
apyawa_culture|Tapirape
enenlhet_culture|Toba-Enenlhet
truka_culture|Truka
lumnana_culture|Chorote
kalimi|Judeo-Persian
macorix_culture|Macoris
tenetehara_culture|Tenetehara
enxet_culture|Enxet Sur
sanaviron_culture|Sanaviron
salar_culture|Salar
tapiiete_culture|Tapiete
lule_culture|Lule
tonokote_culture|Tonocote
tunica_culture|Tunica
sikka_culture|Sika
irritila_culture|Lagunero
gedeo_culture|Gedeo
guanahatabey|Guanahatabey
ciguayo_culture|Ciguayo
cusabo_culture|Cusabo
kvens|Kven Finnish
koroa_culture|Koroa
guana_culture|Guana (Paraguay)
qashqai_culture|Qashqai
igneri|Island Carib
baima_culture|Baima
mehri_culture|Mehri
gothic_culture|Crimean Gothic
yazoo_culture|Yazoo
shihhi_culture|Shihhi Arabic
naso_culture|Teribe
bunak_culture|Bunak
samaritan_culture|Samaritan;Samaritan Aramaic
saluan_culture|Saluan
muna_culture|Muna
helong_culture|Helong
pitlaxa_culture|Pilaga
guarijio_culture|Guarijio
fataluku_culture|Fataluku
banggai_culture|Banggai
rotenese_culture|Roti
gurji|Judeo-Georgian
kukra_culture|Kukra
aikana_culture|Aikana
istroromanian|Istro Romanian
hawu_culture|Hawu
taxliswet_culture|Serrano
nootka_culture|Nuu-chah-nulth
votian|Votic
lomari_culture|Lomavren
comecrudo_culture|Comecrudo
romani_culture|Romani
kwakiutl_culture|Kwakwala
karankawa_culture|Karankawa
wappo_culture|Wappo
yuki_culture|Yuki
manekenk_culture|Haush
haida_culture|Haida
kochini|Jewish Malayalam
haisla_culture|Haisla
heiltsuk_culture|Heiltsuk
oowekyala_culture|Heiltsuk-Oowekyala
kalaw_lagaw_ya_culture|Kala Lagaw Ya
takana_culture|Tacana
abkhazian_culture|Abkhaz
abazin_culture|Abaza
lozi_culture|Luyi
zaza_culture|Zaza
mi_niah_culture|Tangut
ngacang_culture|Achang
kado_culture|Kadu
kuy_culture|Kuay
bru_culture|Bru
merya_culture|Merya
curonian|Curonian
pruthenian|Prussian
semnani_culture|Semnani
dehwar_culture|Dehwari
ambundu|Kimbundu
haneka_humbe|Nyaneka
gurma|Gourmanchema
gurunsi|Grusi
mamprusi|Mampruli
mbunda|Mbunda
luvale|Luvale
luchazi_culture|Luchazi
tumbuka_culture|Tumbuka
nsenga|Nsenga
gula_iro_culture|Gula Iro
sibe_culture|Xibe
sama_culture|Sama-Bajaw
mbugu_culture|Mbugu
ruvu_culture|Ruvu
seuta_culture|Seuta
matuumbi_culture|Matumbi
kallawaya_culture|Callawalla
arawak_culture|Arawak
caquetio_culture|Caquetio
manaos_culture|Manao
pankararu_culture|Pankararu
yuri_culture|Juri
quimbaya_culture|Quimbaya
yarigui_culture|Yarigui
tumaco_culture|Tumaco
monpa_culture|Monpa
tebbu_culture|Tebbu
ava_culture|Guarani
tupiniquim_culture|Tupiniquim
wuyjuyu_culture|Munduruku
catagua_culture|Catagua
satere_mawe_culture|Sateré-Mawé
kagwahiva_culture|Kawahib
kaapor_culture|Kaapor
kawaiwete_culture|Kayabi
tupinamba_culture|Tupinamba
kaete_culture|Kaete
guarasugwe_culture|Guarasugwe
yjxa_culture|Karitiana
makurap_culture|Makurap
awa_canoeiro_culture|Ava-Canoeiro
kukakma_culture|Cocama-Cocamilla
awa_brazil_culture|Guaja
tapajo_culture|Tapajo
arua_culture|Arua
paiter_culture|Suruí of Rondônia
kambeba_culture|Omagua
'''

def catalog():
    rows={r['ID']:r for r in csv.DictReader((DATA/'glottolog-languages.csv').open(encoding='utf-8'))}
    index={}
    for r in rows.values():index.setdefault(norm(r['Name']),set()).add(r['ID'])
    for r in csv.DictReader((DATA/'glottolog-names.csv').open(encoding='utf-8')):
        index.setdefault(norm(r['Name']),set()).add(r['Language_ID'])
    return rows,index

def lookup():
    rows,index=catalog()
    results={}
    for line in QUERIES.strip().splitlines():
        key,terms=line.split('|'); results[key]=[]
        for term in terms.split(';'):
            hits=[rows[i] for i in sorted(index.get(norm(term),())) if i in rows]
            exact=[r for r in hits if norm(r['Name'])==norm(term)]
            selected=exact or hits
            results[key].append((term,selected))
    return results

if __name__=='__main__':
    for key,queries in lookup().items():
        print(key,[(q,[(r['ID'],r['Name'],r['Level'],r['Family_ID']) for r in hits]) for q,hits in queries])

"""Import available EU5 heraldry and build explicit, auditable fallback flags."""
import hashlib
import ast
import operator
import colorsys
import re
from pathlib import Path

from pdx_text import root, Object
from build_m2_prototype import objects, replace_body, patch
from m3_flag_art import contextual_design, compile_design


def resolve_constants(text):
    """Resolve only numeric Clausewitz constants, respecting nested scopes.

    Never eval game data: function calls, attributes and unknown names stay
    unresolved so the individual COA can fall back with an audit reason.
    """
    scopes = [{}]
    ops = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv}
    def calc(expr):
        def visit(n):
            if isinstance(n, ast.Constant) and type(n.value) in (int, float): return n.value
            if isinstance(n, ast.Name):
                for scope in reversed(scopes):
                    if n.id in scope: return scope[n.id]
                raise ValueError(n.id)
            if isinstance(n, ast.BinOp) and type(n.op) in ops:
                return ops[type(n.op)](visit(n.left), visit(n.right))
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
                return visit(n.operand) * (-1 if isinstance(n.op, ast.USub) else 1)
            raise ValueError('Unsupported constant expression')
        return visit(ast.parse(expr.strip(), mode='eval').body)
    token = re.compile(r'#[^\n]*|"[^"\n]*"|@\w+\s*=\s*(?:@\[[^\]]+\]|@\w+|[-+\d.eE]+)|@\[[^\]]+\]|@\w+|[{}]')
    def replace(m):
        s = m[0]
        if s.startswith(('#', '"')): return s
        if s == '{': scopes.append({}); return s
        if s == '}':
            if len(scopes) > 1: scopes.pop()
            return s
        definition = re.match(r'@(\w+)\s*=\s*(.*)', s)
        value = definition[2] if definition else s
        expr = value[2:-1] if value.startswith('@[') else value.lstrip('@')
        try:
            number = calc(expr)
            if definition: scopes[-1][definition[1]] = number; return ''
            return f'{number:.10g}'
        except (ValueError, TypeError, SyntaxError, ZeroDivisionError):
            if definition: scopes[-1][definition[1]] = None
            return s
    return token.sub(replace, text)


def block(key, body):
    return f'{key} = {{\n{body}\n}}\n'


def flag_design(identity, color, religion='', colonial=False, region='', company=False):
    """A restrained heraldic grammar, using assets already shipped with V3."""
    seed = hashlib.sha256(identity.encode('utf-8')).digest()
    palettes = ((132,35,48), (28,66,108), (30,91,67), (84,51,107), (38,45,53), (123,63,34))
    source = list(map(int, color)) if len(color) == 3 else [28,66,108]
    # Match hue to a restrained dark field, rather than a random RGB accent.
    def hue(c):
        total = max(sum(c), 1)
        return [v / total for v in c]
    base = min(palettes, key=lambda p: sum((a-b)**2 for a,b in zip(hue(p), hue(source))))
    metal = (238,198,100) if seed[0] % 2 else (242,236,217)
    motifs = {'catholic':'ce_cross_couped.dds', 'protestant':'ce_cross_couped.dds',
              'orthodox':'ce_cross_couped.dds', 'oriental_orthodox':'ce_cross_couped.dds',
              'sunni':'ce_crescent.dds', 'shiite':'ce_crescent.dds', 'ibadi':'ce_crescent.dds',
              'mahayana':'ce_lotus.dds', 'theravada':'ce_lotus.dds', 'gelugpa':'ce_lotus.dds',
              'hindu':'ce_sun.dds', 'shinto':'ce_sun.dds', 'confucian':'ce_sun.dds'}
    emblem = 'ce_star_05.dds' if colonial else motifs.get(religion, 'ce_sun.dds')
    if emblem == 'ce_cross_couped.dds':
        emblem = ('ce_cross_couped.dds', 'ce_cross_fleury.dds', 'ce_cross_patty.dds')[seed[2] % 3]
    # One balanced charge; colonial charges clear the overlord canton.
    layouts = [('pattern_solid.tga', (.5,.5), (.56,.56)),
               ('pattern_horizontal_split_01.tga', (.5,.25), (.34,.34)),
               ('pattern_vertical_split_01.tga', (.25,.5), (.34,.34))]
    pattern, position, scale = layouts[seed[1] % len(layouts)]
    positions = [position]
    if not colonial and seed[5] % 3:
        count = 2 if seed[5] % 3 == 1 else 3
        if pattern == 'pattern_solid.tga':
            positions = [(.32,.5),(.68,.5)] if count == 2 else [(.5,.28),(.30,.66),(.70,.66)]
            scale = (.28,.28)
        elif pattern == 'pattern_horizontal_split_01.tga':
            positions = [(.32,.25),(.68,.25)] if count == 2 else [(.24,.25),(.5,.25),(.76,.25)]
            scale = (.20,.20)
        else:
            positions = [(.25,.32),(.25,.68)] if count == 2 else [(.25,.24),(.25,.5),(.25,.76)]
            scale = (.20,.20)
        position = positions[0]
    if colonial:
        # A family ensign: the overlord's hue is stable, one territorial badge
        # occupies the fly. Geography supplies a design theme, not a claim to
        # historical arms. Companies use maritime motifs instead.
        themes = {
            '05_north_america': ('ce_wheat_garb.dds', 'ce_sun.dds'),
            '06_central_america': ('ce_palm_tree.dds', 'ce_sun.dds'),
            '07_south_america': ('ce_sun.dds', 'ce_wheat_garb.dds'),
            '03_north_africa': ('ce_palm_tree.dds', 'ce_sun.dds'),
            '04_subsaharan_africa': ('ce_palm_tree.dds', 'ce_wheat_garb.dds'),
            '12_indonesia': ('ce_palm_tree.dds', 'ce_ship_wheel.dds'),
            '13_australasia': ('ce_ship_wheel.dds', 'ce_star_05.dds')}
        motifs = ('ce_ship_wheel.dds', 'ce_ship_manchester.dds') if company else themes.get(region, ('ce_sun.dds', 'ce_wheat_garb.dds'))
        emblem = motifs[seed[2] % len(motifs)]
        pattern = ('pattern_solid.tga', 'pattern_horizontal_split_01.tga', 'pattern_vertical_split_01.tga')[seed[1] % 3]
        position = ((.70,.65), (.72,.64), (.72,.70))[seed[4] % 3]
        size = (.36, .40, .44)[seed[5] % 3]
        scale = (size, size)
        positions = [position]
    layers = []
    if colonial:
        # Layered badge: supporters, a contrasting escutcheon, then one charge.
        # All bounding boxes stay on the fly and outside the dynamic canton.
        shape = ('ce_circle.dds', 'ce_shield_heater.dds', 'ce_shield_iberian.dds')[seed[7] % 3]
        position = (.72, .61)
        ornament = 'ce_laurel.dds' if seed[8] % 2 else 'ce_laurel_circled.dds'
        surround = metal if pattern == 'pattern_solid.tga' else base
        layers.append(dict(emblem=ornament, color=surround, position=position, scale=(.51,.68)))
        layers.append(dict(emblem=shape, color=surround, position=position, scale=(.38,.53)))
        layers.append(dict(emblem=shape, color=metal, position=position, scale=(.34,.48)))
        layers.append(dict(emblem=shape, color=base, position=position, scale=(.30,.43)))
        if seed[9] % 2:
            layers.append(dict(emblem='ce_ribbon.dds', color=surround, position=(.72,.86), scale=(.35,.12)))
        scale=(.21,.28); positions=[position]
    return {'pattern':pattern, 'field':base, 'metal':metal, 'emblem':emblem,
            'position':position, 'positions':positions, 'scale':scale, 'colonial':colonial,
            'region':region, 'company':company,
            'charge_color':metal, 'layers':layers}


def generated_flag(identity, color, religion='', colonial=False, region='', company=False):
    d = flag_design(identity, color, religion, colonial, region, company)
    rgb = lambda c: 'rgb { ' + ' '.join(map(str,c)) + ' }'
    vec = lambda c: '{ ' + ' '.join(f'{v:.2f}' for v in c) + ' }'
    body = f'pattern = "{d["pattern"]}"\ncolor1 = {rgb(d["field"])}\ncolor2 = {rgb(d["metal"])}\n'
    for layer in d['layers']:
        body += block('colored_emblem', f'texture = "{layer["emblem"]}"\ncolor1 = {rgb(layer["color"])}\ncolor2 = {rgb(layer["color"])}\n'
                      + block('instance', f'position = {vec(layer["position"])}\nscale = {vec(layer["scale"])}'))
    body += block('colored_emblem', f'texture = "{d["emblem"]}"\ncolor1 = {rgb(d["charge_color"])}\ncolor2 = {rgb(d["charge_color"])}\n'
                  + ''.join(block('instance', f'position = {vec(pos)}\nscale = {vec(d["scale"])}') for pos in d['positions']))
    return body


class FlagExporter:
    def __init__(self, eu5):
        self.base = eu5 / 'main_menu'
        self.coas = {k: o for p in sorted((self.base / 'common/coat_of_arms/coat_of_arms').glob('*.txt'))
                     for k, o in objects(root(resolve_constants(p.read_text(encoding='utf-8-sig'))))}
        self.flag_lists = {k:o for p in sorted((self.base/'common/flag_definitions').glob('*.txt'))
                           for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
        self.triggers = {k:o for p in sorted((self.base/'common/scripted_triggers').glob('*coa*.txt'))
                         for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
        self.colors = {}
        for p in sorted((self.base / 'common/named_colors').glob('*.txt')):
            for m in re.finditer(r'\b(\w+)\s*=\s*(rgb|hsv360|hsv)\s*\{([^}]+)\}', p.read_text(encoding='utf-8-sig')):
                self.colors[m[1]] = m[2] + ' {' + m[3] + '}'
        self.imported, self.used_colors, self.assets, self.visiting = {}, set(), {}, set()

    def trigger(self, obj, src, age, seen=()):
        """Three-valued evaluation: an unknown condition never qualifies a flag.

        Missing evidence remains unknown; never negate an unknown into true.
        """
        values=[]
        for k,v in obj.entries():
            result=None
            if k in ('AND','OR','NOT','NOR') and isinstance(v,Object):
                parts=[self.trigger(root(block(a,b.text()) if isinstance(b,Object) else f'{a} = {b}'),src,age,seen) for a,b in v.entries()]
                if k in ('OR','NOR'):
                    result=True if True in parts else (None if None in parts else False)
                else: result=False if False in parts else (None if None in parts else True)
                if k in ('NOT','NOR') and result is not None: result=not result
            elif k=='scope:actor' and isinstance(v,Object): result=self.trigger(v,src,age,seen)
            elif k=='current_age' and age: result=v==age
            elif k=='country_rank' and src.get('country_rank'):
                result=src['country_rank']==v.split(':')[-1]
            elif k=='has_variable' and 'variable_names' in src:
                result=v in src['variable_names']
            elif k=='is_subject_type' and 'subject_ids' in src:
                result=src.get('subject_type')==v.split(':')[-1]
            elif k=='capital' and isinstance(v,Object):
                result=self.trigger(v,{'continent':src.get('capital_continent')},age,seen)
            elif k=='continent' and src.get('continent'):
                result=src['continent']==v.split(':')[-1]
            elif k in ('any_subject','any_subject_or_below') and isinstance(v,Object) and 'subject_ids' in src:
                pending=list(src['subject_ids']);visited=set();parts=[]
                while pending:
                    sid=pending.pop()
                    if sid in visited:continue
                    visited.add(sid);child=getattr(self,'source_countries',{}).get(sid)
                    if child is None:parts.append(None);continue
                    parts.append(self.trigger(v,child,age,seen))
                    if k=='any_subject_or_below':pending.extend(child.get('subject_ids',[]))
                result=True if True in parts else None if None in parts else False
            elif k=='government_type': result=src.get('government')==v.split(':')[-1]
            elif k=='has_reform': result=v.split(':')[-1] in src.get('reforms',[])
            elif k=='has_or_had_tag':
                if v in {src.get('flag'),src.get('definition'),*src.get('previous_tags',[])}: result=True
                # The supplement may lack the complete country formation chain.
                elif 'previous_tags' in src: result=False
            elif k in self.triggers and k not in seen and v in ('yes','no'):
                result=self.trigger(self.triggers[k],src,age,seen+(k,))
                if v=='no' and result is not None: result=not result
            values.append(result)
        return False if False in values else (None if None in values else True)

    def candidates(self, src, source_tag, age=None):
        result=[]
        for key in dict.fromkeys(filter(None,(src.get('flag'),source_tag,src.get('definition')))):
            if key in self.flag_lists:
                eligible=[]
                for _,obj in objects(self.flag_lists[key]):
                    f=dict(obj.entries()); coa=f.get('coa')
                    if not isinstance(coa,str) or coa=='list': continue
                    if 'trigger' not in f or self.trigger(f['trigger'],src,age) is True:
                        eligible.append((float(f.get('priority',0)),coa))
                result.extend(coa for _,coa in sorted(eligible,reverse=True))
            result.append(key)
        return list(dict.fromkeys(result))

    def unresolved_candidates(self, src, source_tag, age=None):
        unresolved=[]
        for key in dict.fromkeys(filter(None,(src.get('flag'),source_tag,src.get('definition')))):
            for _,obj in objects(self.flag_lists.get(key,root(''))):
                f=dict(obj.entries())
                if 'trigger' in f and self.trigger(f['trigger'],src,age) is None:
                    unresolved.append({'list':key,'coa':f.get('coa'),'priority':f.get('priority','0'),
                                       'condition':f['trigger'].text().strip()})
        return unresolved

    def resolve(self, src, source_tag, age=None):
        attempts=[]
        for key in self.candidates(src,source_tag,age):
            snapshot=(self.imported.copy(),self.used_colors.copy(),self.assets.copy())
            try: return self.import_coa(key),key,attempts
            except ValueError as error:
                self.imported,self.used_colors,self.assets=snapshot
                attempts.append({'key':key,'reason':str(error)})
        return None,None,attempts

    def heraldry_color(self, key, fallback):
        """First chromatic field tint in the resolved flag, else country map color."""
        if key not in self.coas: return fallback
        header=re.split(r'\b(?:colored_emblem|textured_emblem|sub)\s*=',self.coas[key].text())[0]
        for name in re.findall(r'\bcolor\d+\s*=\s*"?(\w+)"?',header):
            raw=self.colors.get(name,'')
            m=re.fullmatch(r'(rgb|hsv360|hsv)\s*\{([^}]+)\}',raw)
            if not m: continue
            nums=list(map(float,m[2].split()))
            if len(nums)!=3: continue
            if m[1]=='hsv360': nums=list(colorsys.hsv_to_rgb(nums[0]/360,nums[1]/100,nums[2]/100))
            elif m[1]=='hsv': nums=list(colorsys.hsv_to_rgb(*nums))
            elif max(nums)>1: nums=[n/255 for n in nums]
            if max(nums)-min(nums)>.15: return [round(n*255) for n in nums]
        return fallback

    def import_coa(self, key):
        name = 'EU5SRC_' + hashlib.sha256(key.encode()).hexdigest()[:16]
        if name in self.imported: return name
        if key in self.visiting: raise ValueError('Cyclic heraldry parent: ' + key)
        if key not in self.coas: raise ValueError('Source heraldry definition unavailable: ' + str(key))
        self.visiting.add(key)
        try:
            body = self.coas[key].text()
            if '@' in re.sub(r'#[^\n]*', '', body):
                raise ValueError('Source heraldry uses unevaluated variables: ' + key)
            def asset(match):
                kind, filename = match[1], match[2]
                if Path(filename).name != filename: raise ValueError('Unexpected asset path')
                folders = ('patterns',) if kind == 'pattern' else ('colored_emblems', 'textured_emblems')
                candidates = [self.base / 'gfx/coat_of_arms' / folder / filename for folder in folders]
                source = next((p for p in candidates if p.is_file()), None)
                if not source: raise ValueError('Missing source flag texture: ' + filename)
                copied = 'eu5_m3_' + filename
                dest = 'gfx/coat_of_arms/' + source.parent.name + '/' + copied
                self.assets[dest] = source
                return f'{kind} = "{copied}"'
            body = re.sub(r'\b(pattern|texture)\s*=\s*"([^"\n]+)"', asset, body)
            def color(match):
                field, value = match[1], match[2]
                if value in ('rgb', 'hsv', 'hsv360') or re.fullmatch(r'color\d+', value):
                    return match[0]
                if value not in self.colors: raise ValueError('Unknown source named color: ' + value)
                self.used_colors.add(value)
                return f'{field} = "eu5_m3_{value}"'
            body = re.sub(r'\b(color\d+)\s*=\s*"?([A-Za-z_]\w*)"?', color, body)
            body = re.sub(r'\bparent\s*=\s*"?([\w.-]+)"?', lambda m: 'parent = "' + self.import_coa(m[1]) + '"', body)
            self.imported[name] = body
            return name
        finally:
            self.visiting.discard(key)

    def export(self, exporter):
        self.source_countries=exporter.w.politics['countries']
        coas, definitions, report = [], [], []
        generated_bodies = set()
        native_definitions = {}
        parents = {e['target_subject']: e['target_overlord'] for e in exporter.w.edges}
        regions = {state:p.stem for p in sorted((exporter.w.game/'map_data/state_regions').glob('*.txt'))
                   for state,_ in objects(root(p.read_text(encoding='utf-8-sig')))}
        for tag, c in sorted(exporter.w.countries.items()):
            if c.get('generated_uncolonized'):
                coa='eu5_uncolonized_'+tag
                body=generated_flag('uncolonized:'+c['culture']+':'+tag,['100','130','160'])
                coas.append(block(coa,body))
                definitions.append(block(tag,block('flag_definition',f'coa = {coa}\npriority = 1000\n')))
                report.append({'tag':tag,'source_id':None,'mode':'generated_uncolonized_flag',
                               'overlord_canton':False,'limitation':'Procedural identifier, not historical tribal arms.'})
                continue
            if not c['source_id']: continue
            src = exporter.w.politics['countries'][c['source_id']]
            key = src.get('flag') or c['source_tag']
            reason = ''
            parent = parents.get(tag)
            canton = c['country_type'] in ('colonial', 'company') and bool(parent)
            design = None
            coa, resolved_key, attempts = self.resolve(src,c['source_tag'],exporter.w.politics.get('current_age'))
            if coa:
                mode = 'imported_eu5_definition'
            elif tag in exporter.w.country_defs and not canton:
                report.append({'tag':tag,'source_id':c['source_id'],'source_flag_key':key,
                               'mode':'existing_v3_identity_flag','attempts':attempts,
                               'limitation':'Reviewed identity match; no recoverable EU5 scripted COA.'})
                continue
            else:
                reason = '; '.join(a['reason'] for a in attempts)
                coa = 'EU5_FLAG_' + tag
                color = src['color']
                if canton and parent:
                    parent_sid = exporter.w.countries[parent]['source_id']
                    if parent_sid:
                        parent_src=exporter.w.politics['countries'][parent_sid]
                        _,parent_key,_=self.resolve(parent_src,exporter.w.countries[parent]['source_tag'],exporter.w.politics.get('current_age'))
                        color=self.heraldry_color(parent_key,parent_src['color'])
                region = regions.get(c.get('capital'),'')
                company = c['country_type']=='company'
                identity = c['source_id'] + ':' + key
                for variant in range(1024):
                    choice = identity + ':' + str(variant)
                    context=dict(c,flag_features=getattr(exporter.w,'flag_features',{}).get(tag,{}))
                    design = contextual_design(choice, color, context, src, canton, region, company)
                    body = compile_design(design)
                    if body not in generated_bodies: break
                else:
                    body = generated_flag(identity, color)
                    design = None
                    reason += '; contextual design space exhausted; deterministic procedural identifier'
                for layer in (design['layers'] if design else []):
                    filename=layer['emblem']
                    if filename.startswith('eu5_m3_'):
                        source=self.base/'gfx/coat_of_arms/colored_emblems'/filename.removeprefix('eu5_m3_')
                        if not source.is_file():raise ValueError('Missing cultural emblem: '+str(source))
                        self.assets['gfx/coat_of_arms/colored_emblems/'+filename]=source
                generated_bodies.add(body)
                coas.append(block(coa, body))
                mode = 'generated_identity_flag'
            # The overlord must explicitly supply the COA used by its subjects.
            # allow_overlord_canton on the child only enables receiving it.
            definition = f'coa = {coa}\nsubject_canton = {coa}\npriority = 1000\n'
            if canton:
                definition += 'allow_overlord_canton = yes\noverlord_canton_offset = { 0 0 }\noverlord_canton_scale = { 0.4 0.4 }\n'
            if tag in exporter.w.country_defs:
                native_definitions[tag] = block('flag_definition', definition)
            else:
                definitions.append(block(tag, block('flag_definition', definition)))
            report.append({'tag': tag, 'source_id': c['source_id'], 'source_flag_key': key, 'mode': mode,
                           'resolved_source_flag':resolved_key, 'attempts':attempts, 'overlord':parent,
                           'overlord_canton': canton, 'reason': reason,
                           'design': design, 'design_version': 4 if design else None,
                           'limitation': 'Source-supported age/government/reform/tag variants only; unknown dynasty/territory conditions are not assumed.' if mode.startswith('imported')
                                         else 'Generated identity flag; original dynamically generated EU5 flag was not recovered.'})
        coas.extend(block(key, body) for key, body in sorted(self.imported.items()))
        exporter.write('common/coat_of_arms/coat_of_arms/zz_eu5_world.txt', ''.join(coas))
        found = set()
        for path in sorted((exporter.w.game / 'common/flag_definitions').glob('*.txt')):
            relative = path.relative_to(exporter.w.game).as_posix()
            text = exporter.w.read(relative); edits = []
            for tag, obj in objects(root(text)):
                if tag in native_definitions:
                    edits.append(replace_body(obj, '\n' + native_definitions[tag])); found.add(tag)
            if edits: exporter.write(relative, patch(text, edits))
        # Native tags can use the engine's implicit TAG -> COA fallback without
        # an explicit flag list. Give those an explicit source override too.
        definitions.extend(block(tag,native_definitions[tag]) for tag in sorted(native_definitions.keys()-found))
        exporter.write('common/flag_definitions/zz_eu5_world.txt', ''.join(definitions))
        exporter.write('common/named_colors/eu5_m3_flags.txt', block('colors', '\n'.join(f'eu5_m3_{k} = {self.colors[k]}' for k in sorted(self.used_colors))))
        exporter.binary_assets.update(self.assets)
        exporter.flag_report = report

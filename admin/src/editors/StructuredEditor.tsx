import StoryletEditor from './StoryletEditor'

type Json = Record<string, unknown>

function text(value: unknown) { return value == null ? '' : String(value) }
function list(value: unknown) { return Array.isArray(value) ? value.map(String).join(', ') : '' }
function split(value: string) { return value.split(',').map(item => item.trim()).filter(Boolean) }

export default function StructuredEditor({ type, document, onChange }: { type: string; document: Json; onChange: (next: Json) => void }) {
  const patch = (key: string, value: unknown) => onChange({ ...document, [key]: value })
  if (type === 'item') return <div className="form-grid">
    <label>名称<input value={text(document.name)} onChange={event => patch('name', event.target.value)} /></label>
    <label>类型<input value={text(document.type)} onChange={event => patch('type', event.target.value)} /></label>
    <label>价值<input type="number" value={Number(document.value ?? 0)} onChange={event => patch('value', Number(event.target.value))} /></label>
    <label>重量<input type="number" step="0.1" value={Number(document.weight ?? 0)} onChange={event => patch('weight', Number(event.target.value))} /></label>
    <label>护甲<input type="number" value={Number(document.armor ?? 0)} onChange={event => patch('armor', Number(event.target.value))} /></label>
    <label>伤害<input type="number" value={Number(document.damage ?? 0)} onChange={event => patch('damage', Number(event.target.value))} /></label>
    <label>耐久<input type="number" value={Number(document.durability ?? 0)} onChange={event => patch('durability', Number(event.target.value))} /></label>
    <label>保暖<input type="number" value={Number(document.warmth ?? 0)} onChange={event => patch('warmth', Number(event.target.value))} /></label>
    <label className="wide">允许槽位（逗号分隔）<input value={list(document.allowed_slots)} onChange={event => patch('allowed_slots', split(event.target.value))} /></label>
    <label className="wide">占用槽位（逗号分隔）<input value={list(document.occupied_slots)} onChange={event => patch('occupied_slots', split(event.target.value))} /></label>
    <label className="wide">Tags<input value={list(document.tags)} onChange={event => patch('tags', split(event.target.value))} /></label>
    <label className="check wide"><input type="checkbox" checked={!!document.adult_only} onChange={event => patch('adult_only', event.target.checked)} />仅成年人物可用</label>
    <label className="wide">描述<textarea rows={4} value={text(document.description)} onChange={event => patch('description', event.target.value)} /></label>
    <JsonField label="Requirements" value={document.requirements ?? {}} onValid={value => patch('requirements', value)} />
    <JsonField label="属性/领地 Effects" value={document.effects ?? { character_attributes: {}, realm_resources: {} }} onValid={value => patch('effects', value)} />
  </div>
  if (type === 'preset_character') return <div className="form-grid">
    <label>姓名<input value={text(document.name)} onChange={event => patch('name', event.target.value)} /></label>
    <label>人物 kind<input value={text(document.kind)} onChange={event => patch('kind', event.target.value)} /></label>
    <label>性别<input value={text(document.gender)} onChange={event => patch('gender', event.target.value)} /></label>
    <label>年龄<input type="number" min="0" value={Number(document.age ?? 18)} onChange={event => patch('age', Number(event.target.value))} /></label>
    <label>角色/职业<input value={text(document.role)} onChange={event => patch('role', event.target.value)} /></label>
    <label>身体预设<input value={text(document.body_preset_id)} onChange={event => patch('body_preset_id', event.target.value)} /></label>
    <label className="wide">Tags<input value={list(document.tags)} onChange={event => patch('tags', split(event.target.value))} /></label>
    <label className="wide">人物描述<textarea rows={5} value={text(document.description_md)} onChange={event => patch('description_md', event.target.value)} /></label>
    <JsonField label="人物 Components" value={document.components ?? {}} onValid={value => patch('components', value)} />
    <JsonField label="初始 Inventory" value={document.initial_inventory ?? []} onValid={value => patch('initial_inventory', value)} />
    <JsonField label="初始 Equipment" value={document.initial_equipment ?? {}} onValid={value => patch('initial_equipment', value)} />
  </div>
  if (type === 'body_part') return <div className="form-grid">
    <label>显示名称<input value={text(document.label)} onChange={event => patch('label', event.target.value)} /></label>
    <label>类别<input value={text(document.category)} onChange={event => patch('category', event.target.value)} /></label>
    <label>方向<select value={text(document.side)} onChange={event => patch('side', event.target.value)}><option>both</option><option>left</option><option>right</option></select></label>
    <label>父部位<input value={text(document.parent_id)} onChange={event => patch('parent_id', event.target.value || null)} /></label>
    <label>配对部位<input value={text(document.pair_id)} onChange={event => patch('pair_id', event.target.value || null)} /></label>
    <label>性别限制<select value={text(document.sex_restriction || 'any')} onChange={event => patch('sex_restriction', event.target.value)}><option>any</option><option>male</option><option>female</option></select></label>
    <label className="check"><input type="checkbox" checked={!!document.adult_only} onChange={event => patch('adult_only', event.target.checked)} />成人部位</label>
    <label className="wide">Tags<input value={list(document.tags)} onChange={event => patch('tags', split(event.target.value))} /></label>
  </div>
  if (type === 'equipment_slot') return <div className="form-grid">
    <label>显示名称<input value={text(document.label)} onChange={event => patch('label', event.target.value)} /></label>
    <label>身体部位<input value={text(document.body_part_id)} disabled={!!document.virtual} onChange={event => patch('body_part_id', event.target.value || null)} /></label>
    <label>分组<select value={text(document.group)} onChange={event => patch('group', event.target.value)}><option>public</option><option>private</option><option>accessory</option></select></label>
    <label className="check"><input type="checkbox" checked={!!document.virtual} onChange={event => patch('virtual', event.target.checked)} />虚拟槽位</label>
    <label className="check"><input type="checkbox" checked={!!document.adult_only} onChange={event => patch('adult_only', event.target.checked)} />成人槽位</label>
    <label className="wide">常见装备<input value={list(document.examples)} onChange={event => patch('examples', split(event.target.value))} /></label>
  </div>
  if (type === 'body_slot_preset') return <div className="form-grid"><label>名称<input value={text(document.label)} onChange={event => patch('label', event.target.value)} /></label><label className="wide">包含槽位<input value={list(document.slots)} onChange={event => patch('slots', split(event.target.value))} /></label></div>
  if (type === 'character_kind') return <div className="form-grid"><label>名称<input value={text(document.label)} onChange={event => patch('label', event.target.value)} /></label><label className="wide">Components<input value={list(document.components)} onChange={event => patch('components', split(event.target.value))} /></label></div>
  if (type === 'character_attribute') return <div className="form-grid"><label>英文名<input value={text(document.name)} onChange={event => patch('name', event.target.value)} /></label><label>中文名<input value={text(document.label)} onChange={event => patch('label', event.target.value)} /></label><label className="wide">影响<textarea value={text(document.influence)} onChange={event => patch('influence', event.target.value)} /></label></div>
  if (type === 'storylet') {
    return <StoryletEditor document={document} onChange={onChange} />
  }
  return <div className="form-grid"><JsonField label="结构化内容" value={document} onValid={value => onChange(value as Json)} /></div>
}

function JsonField({ label, value, onValid }: { label: string; value: unknown; onValid: (value: unknown) => void }) {
  return <label className="wide">{label}<textarea className="code" rows={8} value={JSON.stringify(value, null, 2)} onChange={event => { try { onValid(JSON.parse(event.target.value)) } catch { /* draft keeps last valid value */ } }} /></label>
}

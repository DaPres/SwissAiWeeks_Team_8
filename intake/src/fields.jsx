import { Field } from '@base-ui/react/field';
import { Select } from '@base-ui/react/select';
import { Check, ChevronDown } from 'lucide-react';

export function TextField({ label, name, value, onChange, hint, multiline, required, ...props }) {
  return <Field.Root name={name} className="field">
    <Field.Label className="label">{label}{required && <span className="required"> *</span>}</Field.Label>
    <Field.Control className="input" render={multiline ? <textarea /> : <input />} value={value} onValueChange={onChange} required={required} {...props} />
    {hint && <Field.Description className="hint">{hint}</Field.Description>}
    <Field.Error className="field-error" />
  </Field.Root>;
}

export function Choice({ label, value, onChange, options, multiple = false, placeholder = 'Select…', hint }) {
  const items = options.map(option => typeof option === 'string' ? { label: option, value: option } : option);
  return <div className="field">
    <Select.Root items={items} value={value} onValueChange={onChange} multiple={multiple}>
      <Select.Label className="label">{label}</Select.Label>
      <Select.Trigger className="input select-trigger">
        <Select.Value placeholder={placeholder}>{selected => multiple ? (selected.length ? selected.join(', ') : placeholder) : (items.find(item => item.value === selected)?.label || placeholder)}</Select.Value>
        <Select.Icon><ChevronDown size={16} /></Select.Icon>
      </Select.Trigger>
      <Select.Portal><Select.Positioner className="select-positioner" sideOffset={6} alignItemWithTrigger={false}>
        <Select.Popup className="select-popup"><Select.List>
          {items.map(item => <Select.Item className="select-item" key={item.value} value={item.value}>
            <Select.ItemText>{item.label}</Select.ItemText><Select.ItemIndicator><Check size={15} /></Select.ItemIndicator>
          </Select.Item>)}
        </Select.List></Select.Popup>
      </Select.Positioner></Select.Portal>
    </Select.Root>
    {hint && <p className="hint">{hint}</p>}
  </div>;
}

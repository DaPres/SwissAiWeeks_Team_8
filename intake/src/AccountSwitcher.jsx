import { useState } from 'react';
import { Popover } from '@base-ui/react/popover';
import { ChevronDown } from 'lucide-react';
import PixelAvatar from './PixelAvatar.jsx';
import { accounts } from './accounts.js';


export default function AccountSwitcher({ account, onChange }) {
  const [open, setOpen] = useState(false);
  const current = accounts.find(item => item.id === account) || accounts[0];
  return <Popover.Root open={open} onOpenChange={setOpen}>
    <Popover.Trigger type="button" className="account-trigger" aria-label={`Switch account, current account ${current.name}, ${current.label}`}>
      <span className="account-identity">
        <PixelAvatar key={current.id} pixels={current.avatar} />
        <span className="account-trigger-text"><span>{current.name}</span><span className="account-caption">{current.label}</span></span>
      </span>
      <ChevronDown size={14} aria-hidden="true" />
    </Popover.Trigger>
    <Popover.Portal><Popover.Positioner side="bottom" align="end" sideOffset={8} collisionPadding={12} className="account-positioner">
      <Popover.Popup className="account-popover">
        <Popover.Title className="sr-only">Switch account</Popover.Title>
        <div className="account-options" role="group" aria-label="Accounts">
          {accounts.map((item, index) => <button key={item.id} type="button" className="account-option" aria-pressed={item.id === account}
            onClick={() => { onChange(item.id); setOpen(false); }}>
            <span className="account-identity"><PixelAvatar pixels={item.avatar} delay={Math.min(index * 18, 144)} /><span className="account-option-label"><span>{item.name}</span><span className="account-caption">{item.label}</span></span></span>
            <span className="account-mark" aria-hidden="true" />
          </button>)}
        </div>
      </Popover.Popup>
    </Popover.Positioner></Popover.Portal>
  </Popover.Root>;
}

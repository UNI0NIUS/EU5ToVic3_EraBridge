"""Allocate valid three-character tags without a 1,296-country prefix ceiling."""
import hashlib
import string


def allocate(identities, reserved=(), preferred_prefix='U'):
    if preferred_prefix not in string.ascii_uppercase:
        raise ValueError('Country tag prefix must be an uppercase letter')
    prefixes=preferred_prefix+''.join(c for c in string.ascii_uppercase if c!=preferred_prefix)
    digits=string.digits+string.ascii_uppercase
    used=set(reserved);result={}
    for identity in sorted(set(identities)):
        start=int(hashlib.sha256(identity.encode()).hexdigest()[:12],16)%1296
        chosen=None
        for prefix in prefixes:
            for offset in range(1296):
                number=(start+offset)%1296
                tag=prefix+digits[number//36]+digits[number%36]
                if tag not in used:chosen=tag;break
            if chosen:break
        if not chosen:raise ValueError('All valid country tags exhausted')
        result[identity]=chosen;used.add(chosen)
    return result

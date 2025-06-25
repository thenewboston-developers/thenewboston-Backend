def to_iso_format(dt, replace_with_z=True):
    isoformat_dt = dt.isoformat()
    if replace_with_z and isoformat_dt.endswith('+00:00'):
        return isoformat_dt.removesuffix('+00:00') + 'Z'

    return isoformat_dt

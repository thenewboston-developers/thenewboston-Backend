from pydantic import constr

hexstr = constr(regex=r'^[0-9a-f]+$', strict=True)

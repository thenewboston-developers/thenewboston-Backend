from typing import Annotated

from pydantic import StringConstraints

hexstr = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]+$', strict=True)]

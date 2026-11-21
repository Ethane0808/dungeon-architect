"""An English message that retains its format arguments for live translation."""


class Message(str):
    def __new__(cls, template: str, **values):
        instance = super().__new__(cls, template.format(**values))
        instance.template = template
        instance.values = values
        return instance

    def __getnewargs_ex__(self):
        return (self.template,), self.values

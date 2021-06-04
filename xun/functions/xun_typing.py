from .compatibility import ast
from .errors import XunSyntaxError
from .util import assignment_target_shape
from .util import flatten_assignment_targets
from .util import indices_from_shape
from immutables import Map as frozenmap
import typing


class XunType:
    def __call__(self, *args, **kwargs):
        raise TypeError('XunType should not be used')

    def __repr__(self):
        return self.__class__.__name__
XunType = XunType()

"""
Xun
Any
Union

Union types (Xun or Any) can't be reused
"""

class TypeDeducer:
    """
    Registers all variables and their types
    """
    def __init__(self, known_xun_functions):
        self.known_xun_functions = known_xun_functions
        self.var_type_map = frozenmap()
        self.local_var_type_map = frozenmap()

    def visit(self, node):
        member = 'visit_' + node.__class__.__name__
        visitor = getattr(self, member)
        return visitor(node)

    def visit_Assign(self, node):
        if len(node.targets) > 1:
            raise SyntaxError("Multiple targets not supported")

        target = node.targets[0]
        target_shape = assignment_target_shape(target)

        value_type = self.visit(node.value)

        if target_shape == (1,):
            target = target
            with self.var_type_map.mutate() as mm:
                mm[target.id] = value_type
                self.var_type_map = mm.finish()
            return value_type

        indices = indices_from_shape(target_shape)
        flatten_targets = flatten_assignment_targets(target)

        with self.var_type_map.mutate() as mm:
            for index, target in zip(indices, flatten_targets):
                target_type = value_type
                if isinstance(target_type, typing.Tuple):
                    for i in index:
                        target_type = target_type.__args__[i]
                mm.set(target.id, target_type)
            self.var_type_map = mm.finish()

        return value_type

    def visit_BoolOp(self, node):
        pass

    def visit_BinOp(self, node):
        left_type = self.visit(node.left)
        right_type = self.visit(node.right)
        if left_type is XunType or right_type is XunType:
            raise XunSyntaxError(
                'Cannot use xun function results as values in xun '
                'definition'
            )
        return typing.Any

    def visit_UnaryOp(self, node):
        pass

    def visit_IfExp(self, node):
        import astor
        body_type = self.visit(node.body)
        orelse_type = self.visit(node.orelse)
        if body_type is not orelse_type:
            return typing.Union[body_type, orelse_type]
        return body_type

    def visit_Dict(self, node: ast.Dict):
        """ We don't support xun keys
        Unknown type, because we can't reason about it (new issue)
        Hence, you can't forward it
        Weak coupling between keys and values
        """

        return {
            self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)
        }
        #typing.Dict[key_type, value_type]

    def visit_Set(self, node):
        """
        Since unordered, all types must be the same
        """
        set_type = self.visit(node.elts[0])
        for elt in node.elts:
            elt_type = self.visit(elt)
            if elt_type is not set_type:
                raise XunSyntaxError

        return set_type

    def visit_ListComp(self, node: ast.ListComp):
        """
        ListComps in Xun produces Tuples (because of posibility for different
        types) -> ListComp means Tuple Comprehension
        Not allowed to iterate over tuples
        Iterator of generators can only be a variable, or a
        Does not support ifs or is_async

        for i in [[1,2,3], [4,5,6]]:
            for k in i:
                (i, k)
        [(i, k) for i in [[1,2,3], [4,5,6]] for k in i]

        """

        # Register the local variables in each generator
        with self.var_type_map.mutate() as mm:
            for generator in node.generators:
                # Deal with iter
                iter_types = self.visit(generator.iter)
                # if hasattr(iter_types, '__origin__') and iter_types.__origin__ is tuple:
                #     raise TypeError('Cannot iterate container of mixed types')

                # Deal with target
                target = generator.target
                target_shape = assignment_target_shape(target)

                if iter_types is None:
                    # Remove eventually
                    continue

                if target_shape == (1,):
                    mm.set(target.id, iter_types)
                    continue

                indices = indices_from_shape(target_shape)
                flatten_targets = flatten_assignment_targets(target)

                for index, target in zip(indices, flatten_targets):
                    target_type = iter_types
                    if hasattr(
                            target_type,
                            '__origin__') and iter_types.__origin__ is tuple:
                        for i in index:
                            target_type = target_type.__args__[i]
                    mm.set(target.id, target_type)

            local_var_type_map = mm.finish()

        self.local_var_type_map = local_var_type_map
        result = self.visit(node.elt)
        self.local_var_type_map = frozenmap()
        return result

    def visit_SetComp(self, node):
        pass

    def visit_DictComp(self, node):
        pass

    def visit_GeneratorExp(self, node):
        pass

    def visit_Await(self, node):
        pass

    def visit_Yield(self, node):
        pass

    def visit_YieldFrom(self, node):
        pass

    def visit_Compare(self, node):
        pass

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Name) and
            node.func.id in self.known_xun_functions):
            return XunType
        return typing.Any

    def visit_FormattedValue(self, node):
        pass

    def visit_JoinedStr(self, node):
        pass

    def visit_Constant(self, node):
        return typing.Any

    def visit_Attribute(self, node):
        pass

    def visit_Subscript(self, node):
        pass

    def visit_Starred(self, node):
        pass

    def visit_Name(self, node: ast.Name):
        if node.id in self.var_type_map.keys():
            return self.var_type_map[node.id]
        if node.id in self.local_var_type_map.keys():
            return self.local_var_type_map[node.id]
        return typing.Any

    def visit_List(self, node):
        pass

    def visit_Tuple(self, node):
        return typing.Tuple.__getitem__(tuple(
            (self.visit(elt) for elt in node.elts)))

    def visit_Slice(self, node):
        pass

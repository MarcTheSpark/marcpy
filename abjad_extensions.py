__author__ = 'mpevans'


from marcpy import barlicity
import copy


# Make quantization search tree based on indigestibility and max pieces

def _make_order_indifferent_tree(sets):
    if sets == [[]]:
        return None
    else:
        out = {}
        flattened_lists = [item for sub_list in sets for item in sub_list]
        possible_values = set(flattened_lists)
        for item in possible_values:
            chains_containing_item = copy.deepcopy([chain for chain in sets if item in chain])
            for chain in chains_containing_item:
                chain.remove(item)
            out[item] = _make_order_indifferent_tree(chains_containing_item)
        return out


def make_search_tree(max_pieces, max_indigestibility):
    allowable_factorizations = [barlicity.prime_factor(n) for n in range(2, max_pieces+1) if
                                barlicity.indigestibility(n) < max_indigestibility]
    return _make_order_indifferent_tree(allowable_factorizations)
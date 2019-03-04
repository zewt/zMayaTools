# Helpers for working with Maya 2019 evaluation cache.

try:
    from maya.plugin.evaluator import CacheEvaluatorManager, cache_preferences
    from maya.app.prefs.OptionVarManager import OptionVarManager
except ImportError:
    # Do nothing on earlier versions of Maya.
    CacheEvaluatorManager = None

_cache_rules = ('CACHE_STANDARD_MODE_VP2_HW', 'CACHE_STANDARD_MODE_VP2_SW', 'CACHE_STANDARD_MODE_EVAL')

def _make_rule(node_type):
    return {
        'newFilter': 'nodeTypes',
        'newFilterParam': 'types=+%s' % node_type,
        'newAction': 'enableEvaluationCache'
    }

def enable_caching_for_node_name(node_type):
    """
    Add node_type to the list of cachable nodes if it's not already present.
    """
    if CacheEvaluatorManager is None:
        return

    rule = _make_rule(node_type)

    # Add the rule to each cache mode.
    for mode in _cache_rules:
        cache_rules = getattr(CacheEvaluatorManager, mode)
        if rule not in cache_rules:
            cache_rules.insert(0, rule)

    # Make sure cache sees our changes.
    optvar = OptionVarManager.option_vars.get('cachedPlaybackMode')
    if optvar is not None:
        optvar.set_state_from_preference()

def disable_caching_for_node_name(node_type):
    """
    Remove node_type from the list of cachable nodes.
    """
    if CacheEvaluatorManager is None:
        return

    rule = _make_rule(node_type)
    for mode in _cache_rules:
        cache_rules = getattr(CacheEvaluatorManager, mode)
        if rule in cache_rules:
            cache_rules.remove(rule)

    # Make sure cache sees our changes.
    cache_preferences.OptionVarManager.set_state_from_preferences()


"""Verify that signed package evidence covers this exact source closure."""
import hashlib
import json


def verify(validation, lock_bytes):
    lock = json.loads(lock_bytes)
    if (validation.get('mac_unit_suite') is not True
            or validation.get('mac_integration_suite') is not True
            or validation.get('integration_scope') != 'omarchy-mac'
            or validation.get('runtime_tests') != lock['validation']['mac_runtime_tests']
            or not validation.get('runtime_tests')
            or validation.get('sources_lock_sha256') != hashlib.sha256(lock_bytes).hexdigest()
            or validation.get('mac_source') != lock['omarchy_mac']['commit']
            or validation.get('runtime_source') != lock['omarchy']['commit']):
        raise ValueError('overlay lacks matching, passing source compatibility evidence')

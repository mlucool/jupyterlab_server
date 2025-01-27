"""Tornado handlers for frontend config storage."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import json
import os
from glob import glob

import json5
from jsonschema import Draft4Validator as Validator
from jsonschema import ValidationError
from jupyter_server.extension.handler import ExtensionHandlerJinjaMixin, ExtensionHandlerMixin
from jupyter_server.services.config.manager import ConfigManager, recursive_update
from tornado import web

from .server import APIHandler, tz

# The JupyterLab settings file extension.
SETTINGS_EXTENSION = '.jupyterlab-settings'


def _get_schema(schemas_dir, schema_name, overrides, labextensions_path):
    """Returns a dict containing a parsed and validated JSON schema."""


    notfound_error = 'Schema not found: %s'
    parse_error = 'Failed parsing schema (%s): %s'
    validation_error = 'Failed validating schema (%s): %s'

    path = None

    # Look for the setting in all of the labextension paths first
    # Use the first one
    if labextensions_path is not None:
        ext_name, _, plugin_name = schema_name.partition(':')
        for ext_path in labextensions_path:
            target = os.path.join(ext_path, ext_name, 'schemas', ext_name, plugin_name + '.json')
            if os.path.exists(target):
                schemas_dir = os.path.join(ext_path, ext_name, 'schemas')
                path = target
                break

    # Fall back on the default location
    if path is None:
        path = _path(schemas_dir, schema_name)

    if not os.path.exists(path):
        raise web.HTTPError(404, notfound_error % path)

    with open(path, encoding='utf-8') as fid:
        # Attempt to load the schema file.
        try:
            schema = json.load(fid)
        except Exception as e:
            name = schema_name
            raise web.HTTPError(500, parse_error % (name, str(e)))

    schema = _override(schema_name, schema, overrides)

    # Validate the schema.
    try:
        Validator.check_schema(schema)
    except Exception as e:
        name = schema_name
        raise web.HTTPError(500, validation_error % (name, str(e)))

    version = _get_version(schemas_dir, schema_name)

    return schema, version


def _get_user_settings(settings_dir, schema_name, schema):
    """
    Returns a dictionary containing the raw user settings, the parsed user
    settings, a validation warning for a schema, and file times.
    """
    path = _path(settings_dir, schema_name, False, SETTINGS_EXTENSION)
    raw = '{}'
    settings = {}
    warning = None
    validation_warning = 'Failed validating settings (%s): %s'
    parse_error = 'Failed loading settings (%s): %s'
    last_modified = None
    created = None

    if os.path.exists(path):
        stat = os.stat(path)
        last_modified = tz.utcfromtimestamp(stat.st_mtime).isoformat()
        created = tz.utcfromtimestamp(stat.st_ctime).isoformat()
        with open(path, encoding='utf-8') as fid:
            try:  # to load and parse the settings file.
                raw = fid.read() or raw
                settings = json5.loads(raw)
            except Exception as e:
                raise web.HTTPError(500, parse_error % (schema_name, str(e)))

    # Validate the parsed data against the schema.
    if len(settings):
        validator = Validator(schema)
        try:
            validator.validate(settings)
        except ValidationError as e:
            warning = validation_warning % (schema_name, str(e))
            raw = '{}'

    return dict(
        raw=raw,
        settings=settings,
        warning=warning,
        last_modified=last_modified,
        created=created
    )


def _get_version(schemas_dir, schema_name):
    """Returns the package version for a given schema or 'N/A' if not found."""

    path = _path(schemas_dir, schema_name)
    package_path = os.path.join(os.path.split(path)[0], 'package.json.orig')

    try:  # to load and parse the package.json.orig file.
        with open(package_path, encoding='utf-8') as fid:
            package = json.load(fid)
            return package['version']
    except Exception:
        return 'N/A'


def _list_settings(schemas_dir, settings_dir, overrides, extension='.json', labextensions_path=None):
    """
    Returns a tuple containing:
     - the list of plugins, schemas, and their settings,
       respecting any defaults that may have been overridden.
     - the list of warnings that were generated when
       validating the user overrides against the schemas.
    """

    settings = {}
    federated_settings = {}
    warnings = []

    if not os.path.exists(schemas_dir):
        warnings = ['Settings directory does not exist at %s' % schemas_dir]
        return ([], warnings)

    schema_pattern = schemas_dir + '/**/*' + extension
    schema_paths = [path for path in glob(schema_pattern, recursive=True)]
    schema_paths.sort()

    for schema_path in schema_paths:
        # Generate the schema_name used to request individual settings.
        rel_path = os.path.relpath(schema_path, schemas_dir)
        rel_schema_dir, schema_base = os.path.split(rel_path)
        id = schema_name = ':'.join([
            rel_schema_dir,
            schema_base[:-len(extension)]  # Remove file extension.
        ]).replace('\\', '/')               # Normalize slashes.
        schema, version = _get_schema(schemas_dir, schema_name, overrides, None)
        user_settings = _get_user_settings(settings_dir, schema_name, schema)

        if user_settings["warning"]:
            warnings.append(user_settings.pop('warning'))

        # Add the plugin to the list of settings.
        settings[id] = dict(
            id=id,
            schema=schema,
            version=version,
            **user_settings
        )

    if labextensions_path is not None:
        schema_paths = []
        for ext_dir in labextensions_path:
            schema_pattern = ext_dir + '/**/schemas/**/*' + extension
            schema_paths.extend([path for path in glob(schema_pattern, recursive=True)])

        schema_paths.sort()

        for schema_path in schema_paths:
            schema_path = schema_path.replace(os.sep, '/')

            base_dir, rel_path = schema_path.split('schemas/')

            # Generate the schema_name used to request individual settings.
            rel_schema_dir, schema_base = os.path.split(rel_path)
            id = schema_name = ':'.join([
                rel_schema_dir,
                schema_base[:-len(extension)]  # Remove file extension.
            ]).replace('\\', '/')               # Normalize slashes.

            # bail if we've already handled the highest federated setting
            if id in federated_settings:
                continue

            schema, version = _get_schema(schemas_dir, schema_name, overrides, labextensions_path=labextensions_path)
            user_settings = _get_user_settings(settings_dir, schema_name, schema)

            if user_settings["warning"]:
                warnings.append(user_settings.pop('warning'))

            # Add the plugin to the list of settings.
            federated_settings[id] = dict(
                id=id,
                schema=schema,
                version=version,
                **user_settings
            )

    settings.update(federated_settings)
    settings_list = [settings[key] for key in sorted(settings.keys(), reverse=True)]

    return (settings_list, warnings)


def _override(schema_name, schema, overrides):
    """Override default values in the schema if necessary."""

    if schema_name in overrides:
        defaults = overrides[schema_name]
        for key in defaults:
            if key in schema['properties']:
                schema['properties'][key]['default'] = defaults[key]
            else:
                schema['properties'][key] = dict(default=defaults[key])

    return schema


def _path(root_dir, schema_name, make_dirs=False, extension='.json'):
    """
    Returns the local file system path for a schema name in the given root
    directory. This function can be used to filed user overrides in addition to
    schema files. If the `make_dirs` flag is set to `True` it will create the
    parent directory for the calculated path if it does not exist.
    """

    parent_dir = root_dir
    notfound_error = 'Settings not found (%s)'
    write_error = 'Failed writing settings (%s): %s'

    try:  # to parse path, e.g. @jupyterlab/apputils-extension:themes.
        package_dir, plugin = schema_name.split(':')
        parent_dir = os.path.join(root_dir, package_dir)
        path = os.path.join(parent_dir, plugin + extension)
    except Exception:
        raise web.HTTPError(404, notfound_error % schema_name)

    if make_dirs and not os.path.exists(parent_dir):
        try:
            os.makedirs(parent_dir)
        except Exception as e:
            raise web.HTTPError(500, write_error % (schema_name, str(e)))

    return path


def _get_overrides(app_settings_dir):
    """Get overrides settings from `app_settings_dir`."""
    overrides, error = {}, ""
    overrides_path = os.path.join(app_settings_dir, 'overrides.json')
    if os.path.exists(overrides_path):
        with open(overrides_path, encoding='utf-8') as fid:
            try:
                overrides = json.load(fid)
            except Exception as e:
                error = e
    # Allow `default_settings_overrides.json` files in <jupyter_config>/labconfig dirs
    # to allow layering of defaults
    cm = ConfigManager(config_dir_name="labconfig")
    recursive_update(overrides, cm.get('default_setting_overrides'))

    return overrides, error


def get_settings(app_settings_dir, schemas_dir, settings_dir, schema_name="", overrides=None, labextensions_path=None):
    """
    Get setttings.

    Parameters
    ----------
    app_settings_dir:
        Path to applications settings.
    schemas_dir: str
        Path to schemas.
    settings_dir:
        Path to settings.
    schema_name str, optional
        Schema name. Default is "".
    overrides: dict, optional
        Settings overrides. If not provided, the overrides will be loaded
        from the `app_settings_dir`. Default is None.
    labextensions_path: list, optional
        List of paths to federated labextensions containing their own schema files.

    Returns
    -------
    tuple
        The first item is a dictionary with a list of setting if no `schema_name`
        was provided, otherwise it is a dictionary with id, raw, scheme, settings
        and version keys. The second item is a list of warnings. Warnings will
        either be a list of i) strings with the warning messages or ii) `None`.
    """
    result = {}
    warnings = []

    if overrides is None:
        overrides, _error = _get_overrides(app_settings_dir)

    if schema_name:
        schema, version = _get_schema(schemas_dir, schema_name, overrides, labextensions_path)
        user_settings = _get_user_settings(settings_dir, schema_name, schema)
        warnings = [user_settings.pop('warning')]
        result = {
            "id": schema_name,
            "schema": schema,
            "version": version,
            **user_settings
        }
    else:
        settings_list, warnings = _list_settings(schemas_dir, settings_dir, overrides, labextensions_path=labextensions_path)
        result = {
            "settings": settings_list,
        }

    return result, warnings


class SettingsHandler(ExtensionHandlerMixin, ExtensionHandlerJinjaMixin, APIHandler):

    def initialize(self, name, app_settings_dir, schemas_dir, settings_dir, labextensions_path, **kwargs):
        super().initialize(name)
        self.overrides, error = _get_overrides(app_settings_dir)
        self.app_settings_dir = app_settings_dir
        self.schemas_dir = schemas_dir
        self.settings_dir = settings_dir
        self.labextensions_path = labextensions_path

        if error:
            overrides_warning = 'Failed loading overrides: %s'
            self.log.warn(overrides_warning % str(error))

    @web.authenticated
    def get(self, schema_name=""):
        """Get setting(s)"""
        result, warnings = get_settings(
            self.app_settings_dir,
            self.schemas_dir,
            self.settings_dir,
            labextensions_path=self.labextensions_path,
            schema_name=schema_name,
            overrides=self.overrides,
        )

        # Print all warnings.
        for w in warnings:
            if w:
                self.log.warn(w)

        return self.finish(json.dumps(result))

    @web.authenticated
    def put(self, schema_name):
        """Update a setting"""
        overrides = self.overrides
        schemas_dir = self.schemas_dir
        settings_dir = self.settings_dir
        settings_error = 'No current settings directory'
        invalid_json_error = 'Failed parsing JSON payload: %s'
        invalid_payload_format_error = 'Invalid format for JSON payload. Must be in the form {\'raw\': ...}'
        validation_error = 'Failed validating input: %s'

        if not settings_dir:
            raise web.HTTPError(500, settings_error)

        raw_payload = self.request.body.strip().decode('utf-8')
        try:
            raw_settings = json.loads(raw_payload)['raw']
            payload = json5.loads(raw_settings)
        except json.decoder.JSONDecodeError as e:
            raise web.HTTPError(400, invalid_json_error % str(e))
        except (KeyError, TypeError) as e:
            raise web.HTTPError(400, invalid_payload_format_error)

        # Validate the data against the schema.
        schema, _ = _get_schema(schemas_dir, schema_name, overrides, labextensions_path=self.labextensions_path)
        validator = Validator(schema)
        try:
            validator.validate(payload)
        except ValidationError as e:
            raise web.HTTPError(400, validation_error % str(e))

        # Write the raw data (comments included) to a file.
        path = _path(settings_dir, schema_name, True, SETTINGS_EXTENSION)
        with open(path, 'w', encoding='utf-8') as fid:
            fid.write(raw_settings)

        self.set_status(204)

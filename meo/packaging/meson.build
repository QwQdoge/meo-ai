python = import('python')
meo_python = python.find_installation('python3')
meo_pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
meo_moduledir = join_paths(meo_pkgdatadir, 'meo')
meo_bindir = join_paths(get_option('prefix'), get_option('bindir'))

meo_conf = configuration_data()
meo_conf.set('PYTHON', meo_python.path())
meo_conf.set('pkgdatadir', meo_pkgdatadir)
meo_conf.set('bindir', meo_bindir)

configure_file(
  input: 'meo-agent-service.in',
  output: 'meo-agent-service',
  configuration: meo_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr--r--'
)

configure_file(
  input: 'meo-ai-usage.in',
  output: 'meo-ai-usage',
  configuration: meo_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr--r--'
)

configure_file(
  input: 'meo-agentd.in',
  output: 'meo-agentd',
  configuration: meo_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr--r--'
)

configure_file(
  input: 'meo-connect-device.in',
  output: 'meo-connect-device',
  configuration: meo_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr--r--'
)

configure_file(
  input: 'meo-agent-service.service.in',
  output: 'meo-agent-service.service',
  configuration: meo_conf,
  install: true,
  install_dir: join_paths(get_option('libdir'), 'systemd', 'user')
)

configure_file(
  input: 'meo-agentd.service.in',
  output: 'meo-agentd.service',
  configuration: meo_conf,
  install: true,
  install_dir: join_paths(get_option('libdir'), 'systemd', 'user')
)

install_data(
  '../runtime/main.py',
  '../runtime/headless_probe.py',
  '../runtime/http_transport.py',
  '../runtime/native_http_transport.py',
  '../runtime/event_journal.py',
  install_dir: join_paths(meo_moduledir, 'runtime')
)

install_data(
  '../service/backend_adapter.py',
  '../service/content_blocks.py',
  '../service/controls.py',
  '../service/core.py',
  '../service/legacy_v2_bridge.py',
  '../service/memory.py',
  '../service/model_roles.py',
  '../service/presentation.py',
  '../service/request_registry.py',
  '../service/request_state.py',
  '../service/resources.py',
  '../service/response_meta.py',
  '../service/search_trace.py',
  '../service/sync_contract.py',
  '../service/tool_decision.py',
  install_dir: join_paths(meo_moduledir, 'service')
)

install_data(
  '../system/system_tool.py',
  '../system/dbus_router.py',
  install_dir: join_paths(meo_moduledir, 'system')
)

install_data(
  '../adapters/control_backend.py',
  '../adapters/headless_newelle.py',
  '../adapters/legacy_chat.py',
  '../adapters/legacy_controls.py',
  '../adapters/legacy_memory.py',
  '../adapters/presentation_legacy_chat.py',
  '../adapters/presentation_tools.py',
  '../adapters/system_tools.py',
  install_dir: join_paths(meo_moduledir, 'adapters')
)

install_data(
  '../usage/__init__.py',
  '../usage/collector.py',
  '../usage/cli.py',
  install_dir: join_paths(meo_moduledir, 'usage')
)

install_data(
  '../device/agentd.py',
  '../device/config.py',
  '../device/events.py',
  '../device/executor.py',
  '../device/main.py',
  '../device/pairing_client.py',
  '../device/protocol.py',
  '../device/runtime.py',
  '../device/secrets.py',
  '../device/websocket_transport.py',
  '../device/workspace_bridge.py',
  install_dir: join_paths(meo_moduledir, 'device')
)

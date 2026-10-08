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
  input: 'meo-agent-service.service.in',
  output: 'meo-agent-service.service',
  configuration: meo_conf,
  install: true,
  install_dir: join_paths(get_option('libdir'), 'systemd', 'user')
)

install_data(
  '../runtime/main.py',
  '../runtime/headless_probe.py',
  '../runtime/http_transport.py',
  '../runtime/event_journal.py',
  install_dir: join_paths(meo_moduledir, 'runtime')
)

install_data(
  '../service/backend_adapter.py',
  '../service/core.py',
  '../service/legacy_v2_bridge.py',
  '../service/request_registry.py',
  '../service/request_state.py',
  '../service/tool_decision.py',
  install_dir: join_paths(meo_moduledir, 'service')
)

install_data(
  '../adapters/headless_newelle.py',
  '../adapters/legacy_chat.py',
  install_dir: join_paths(meo_moduledir, 'adapters')
)

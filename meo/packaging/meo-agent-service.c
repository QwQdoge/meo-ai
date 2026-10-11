#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MEO_PKGDATADIR
#define MEO_PKGDATADIR "/usr/share/newelle"
#endif

static int reject_backend_override(int argc, char **argv)
{
    for (int index = 1; index < argc; ++index) {
        const char *value = argv[index];
        if (strcmp(value, "--backend-factory") == 0
            || strncmp(value, "--backend-factory=", 18) == 0) {
            fprintf(stderr,
                    "meo-agent-service: packaged runtime does not allow backend-factory overrides\n");
            return 1;
        }
    }
    return 0;
}

static void exit_on_python_status(PyStatus status, PyConfig *config)
{
    if (!PyStatus_Exception(status))
        return;
    PyConfig_Clear(config);
    Py_ExitStatusException(status);
}

int main(int argc, char **argv)
{
    if (reject_backend_override(argc, argv))
        return 2;

    /*
     * This executable is an Account-authorized caller. Keep Python's import
     * boundary deterministic: ignore PYTHONPATH, user-site packages and other
     * interpreter environment overrides, then prepend only the root-owned Meo
     * package directory. Development overrides can still run
     * `python -m meo.runtime.main` directly; the installed trusted host cannot.
     */
    if (setenv("MEO_AI_BACKEND_FACTORY",
               "meo.adapters.headless_newelle:create_backend", 1) != 0) {
        perror("meo-agent-service: setenv");
        return 2;
    }

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.parse_argv = 0;

    PyStatus status = PyConfig_SetBytesArgv(&config, argc, argv);
    exit_on_python_status(status, &config);
    status = Py_InitializeFromConfig(&config);
    exit_on_python_status(status, &config);
    PyConfig_Clear(&config);

    int exit_code = 1;
    PyObject *sys_path = PySys_GetObject("path"); /* borrowed */
    PyObject *package_path = PyUnicode_FromString(MEO_PKGDATADIR);
    if (sys_path == NULL || package_path == NULL
        || PyList_Insert(sys_path, 0, package_path) != 0) {
        Py_XDECREF(package_path);
        PyErr_Print();
        goto finalize;
    }
    Py_DECREF(package_path);

    PyObject *module = PyImport_ImportModule("meo.runtime.main");
    if (module == NULL) {
        PyErr_Print();
        goto finalize;
    }
    PyObject *main_function = PyObject_GetAttrString(module, "main");
    if (main_function == NULL || !PyCallable_Check(main_function)) {
        fprintf(stderr, "meo-agent-service: meo.runtime.main.main is unavailable\n");
        PyErr_Print();
        Py_XDECREF(main_function);
        Py_DECREF(module);
        goto finalize;
    }

    PyObject *arguments = PyList_New(argc > 1 ? argc - 1 : 0);
    if (arguments == NULL) {
        Py_DECREF(main_function);
        Py_DECREF(module);
        PyErr_Print();
        goto finalize;
    }
    for (int index = 1; index < argc; ++index) {
        PyObject *value = PyUnicode_DecodeLocale(argv[index], NULL);
        if (value == NULL) {
            Py_DECREF(arguments);
            Py_DECREF(main_function);
            Py_DECREF(module);
            PyErr_Print();
            goto finalize;
        }
        PyList_SET_ITEM(arguments, index - 1, value); /* steals value */
    }

    PyObject *result = PyObject_CallFunctionObjArgs(main_function, arguments, NULL);
    Py_DECREF(arguments);
    Py_DECREF(main_function);
    Py_DECREF(module);
    if (result == NULL) {
        PyErr_Print();
        goto finalize;
    }
    if (result == Py_None) {
        exit_code = 0;
    } else {
        const long value = PyLong_AsLong(result);
        if (value == -1 && PyErr_Occurred()) {
            PyErr_Print();
        } else if (value >= 0 && value <= 255) {
            exit_code = (int)value;
        } else {
            fprintf(stderr, "meo-agent-service: runtime returned an invalid exit code\n");
        }
    }
    Py_DECREF(result);

finalize:
    if (Py_FinalizeEx() < 0 && exit_code == 0)
        exit_code = 120;
    return exit_code;
}

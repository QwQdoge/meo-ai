cmake_minimum_required(VERSION 3.21)
project(MeoAI VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
include(CTest)
find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Quick QuickControls2 Network)
set(MEO_UI_ROOT "" CACHE PATH "MeoUI source directory")
if(NOT EXISTS "${MEO_UI_ROOT}/CMakeLists.txt")
    message(FATAL_ERROR "Set MEO_UI_ROOT to a MeoUI checkout")
endif()
set(MEOUI_BUILD_SHOWCASE OFF CACHE BOOL "" FORCE)
# Build the dependency without its own test suite; our native transport tests
# remain enabled below.
set(BUILD_TESTING_SAVED ${BUILD_TESTING})
set(BUILD_TESTING OFF)
add_subdirectory("${MEO_UI_ROOT}" meoui)
set(BUILD_TESTING ${BUILD_TESTING_SAVED})
qt_add_executable(meo-ai app/main.cpp app/agentclient.cpp app/agentclient.h)
qt_add_resources(meo-ai "meo_app" PREFIX "/meo" FILES app/qml/Main.qml)
add_dependencies(meo-ai meoui_moduleplugin)
target_link_libraries(meo-ai PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Network)
if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    qt_add_executable(meo-ai-client-test tests/client-test.cpp app/agentclient.cpp app/agentclient.h)
    target_include_directories(meo-ai-client-test PRIVATE app)
    target_link_libraries(meo-ai-client-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.transport COMMAND meo-ai-client-test)

    qt_add_executable(meo-ai-early-cancel-test tests/early-cancel-test.cpp app/agentclient.cpp app/agentclient.h)
    target_include_directories(meo-ai-early-cancel-test PRIVATE app)
    target_link_libraries(meo-ai-early-cancel-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.early-cancel COMMAND meo-ai-early-cancel-test)

    qt_add_executable(meo-ai-service-recovery-test tests/service-recovery-test.cpp app/agentclient.cpp app/agentclient.h)
    target_include_directories(meo-ai-service-recovery-test PRIVATE app)
    target_link_libraries(meo-ai-service-recovery-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.service-recovery COMMAND meo-ai-service-recovery-test)

    qt_add_executable(meo-ai-history-restore-test tests/history-restore-test.cpp app/agentclient.cpp app/agentclient.h)
    target_include_directories(meo-ai-history-restore-test PRIVATE app)
    target_link_libraries(meo-ai-history-restore-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.history-restore COMMAND meo-ai-history-restore-test)

    qt_add_executable(meo-ai-stale-conversation-recovery-test tests/stale-conversation-recovery-test.cpp app/agentclient.cpp app/agentclient.h)
    target_include_directories(meo-ai-stale-conversation-recovery-test PRIVATE app)
    target_link_libraries(meo-ai-stale-conversation-recovery-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.stale-conversation-recovery COMMAND meo-ai-stale-conversation-recovery-test)

    add_test(
        NAME meo-ai.default-transport
        COMMAND ${CMAKE_COMMAND} -E env
            --unset=MEO_AI_SERVICE_ENDPOINT
            --unset=MEO_AI_ENDPOINT
            $<TARGET_FILE:meo-ai> --print-transport
    )
    set_tests_properties(meo-ai.default-transport PROPERTIES PASS_REGULAR_EXPRESSION "service")

    add_test(
        NAME meo-ai.legacy-fallback-transport
        COMMAND ${CMAKE_COMMAND} -E env
            --unset=MEO_AI_SERVICE_ENDPOINT
            MEO_AI_ENDPOINT=http://127.0.0.1:8080
            $<TARGET_FILE:meo-ai> --print-transport
    )
    set_tests_properties(meo-ai.legacy-fallback-transport PROPERTIES PASS_REGULAR_EXPRESSION "legacy")

    add_test(NAME meo-ai.qml-smoke COMMAND meo-ai --smoke)
    set_tests_properties(meo-ai.qml-smoke PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QSG_RHI_BACKEND=software")
endif()
include(GNUInstallDirs)
install(TARGETS meo-ai RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY prompts skills DESTINATION ${CMAKE_INSTALL_DATADIR}/meo-ai)
target_compile_definitions(meo-ai PRIVATE MEOUI_IMPORT_PATH="${CMAKE_CURRENT_BINARY_DIR}/meoui")

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

set(MEO_AGENT_CLIENT_SOURCES
    app/agentclient.cpp
    app/agentclient_resources.cpp
    app/agentclient.h
)

set(MEO_USAGE_SOURCES
    app/usagebackend.cpp
    app/usagebackend.h
)

set(MEO_APP_QML
    app/qml/Main.qml
    app/qml/AiLogo.qml
    app/qml/ResponseDetails.qml
    app/qml/ResponseContent.qml
    app/qml/DetailsPane.qml
    app/qml/ActivityDashboard.qml
    app/qml/PresentationCard.qml
    app/qml/NavigationButton.qml
    app/qml/AiControlsPopup.qml
    app/qml/MemoryPanel.qml
    app/qml/LongPastePanel.qml
)

qt_add_executable(meo-ai app/main.cpp ${MEO_AGENT_CLIENT_SOURCES} ${MEO_USAGE_SOURCES})
qt_add_resources(meo-ai "meo_app" PREFIX "/meo" FILES ${MEO_APP_QML})
add_dependencies(meo-ai meoui_moduleplugin)
target_link_libraries(meo-ai PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Network)
if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    qt_add_executable(meo-ai-ui-layout-test tests/ui-layout-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-ui-layout-test PRIVATE app)
    target_link_libraries(meo-ai-ui-layout-test PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Network Qt6::Test)
    add_dependencies(meo-ai-ui-layout-test meoui_moduleplugin)
    qt_add_resources(meo-ai-ui-layout-test "meo_layout_app" PREFIX "/meo" FILES ${MEO_APP_QML})
    target_compile_definitions(meo-ai-ui-layout-test PRIVATE MEOUI_IMPORT_PATH="${CMAKE_CURRENT_BINARY_DIR}/meoui")
    add_test(NAME meo-ai.ui-layout COMMAND meo-ai-ui-layout-test)
    set_tests_properties(meo-ai.ui-layout PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QSG_RHI_BACKEND=software")
    # Live use still requires an explicit endpoint. CTest only runs this client
    # against a local Python stub; it never uses a configured provider/profile.
    qt_add_executable(meo-ai-live-client tests/live-native-client.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-live-client PRIVATE app)
    target_link_libraries(meo-ai-live-client PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Network)
    add_dependencies(meo-ai-live-client meoui_moduleplugin)
    qt_add_resources(meo-ai-live-client "meo_live_app" PREFIX "/meo" FILES ${MEO_APP_QML})
    target_compile_definitions(meo-ai-live-client PRIVATE MEOUI_IMPORT_PATH="${CMAKE_CURRENT_BINARY_DIR}/meoui")
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_test(NAME meo-ai.service-integration
        COMMAND ${CMAKE_COMMAND} -E env
            MEO_AI_NATIVE_TEST_CLIENT=$<TARGET_FILE:meo-ai-live-client>
            ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_native_service_integration.py)
    set_tests_properties(meo-ai.service-integration PROPERTIES TIMEOUT 60)
    qt_add_executable(meo-ai-client-test tests/client-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-client-test PRIVATE app)
    target_link_libraries(meo-ai-client-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.transport COMMAND meo-ai-client-test)

    qt_add_executable(meo-ai-early-cancel-test tests/early-cancel-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-early-cancel-test PRIVATE app)
    target_link_libraries(meo-ai-early-cancel-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.early-cancel COMMAND meo-ai-early-cancel-test)

    qt_add_executable(meo-ai-service-recovery-test tests/service-recovery-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-service-recovery-test PRIVATE app)
    target_link_libraries(meo-ai-service-recovery-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.service-recovery COMMAND meo-ai-service-recovery-test)

    qt_add_executable(meo-ai-history-restore-test tests/history-restore-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-history-restore-test PRIVATE app)
    target_link_libraries(meo-ai-history-restore-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.history-restore COMMAND meo-ai-history-restore-test)

    qt_add_executable(meo-ai-stale-conversation-recovery-test tests/stale-conversation-recovery-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-stale-conversation-recovery-test PRIVATE app)
    target_link_libraries(meo-ai-stale-conversation-recovery-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.stale-conversation-recovery COMMAND meo-ai-stale-conversation-recovery-test)

    qt_add_executable(meo-ai-service-metadata-test tests/service-metadata-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-service-metadata-test PRIVATE app)
    target_link_libraries(meo-ai-service-metadata-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.service-metadata COMMAND meo-ai-service-metadata-test)

    qt_add_executable(meo-ai-presentation-event-test tests/presentation-event-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-presentation-event-test PRIVATE app)
    target_link_libraries(meo-ai-presentation-event-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.presentation-event COMMAND meo-ai-presentation-event-test)

    qt_add_executable(meo-ai-resource-client-test tests/resource-client-test.cpp ${MEO_AGENT_CLIENT_SOURCES})
    target_include_directories(meo-ai-resource-client-test PRIVATE app)
    target_link_libraries(meo-ai-resource-client-test PRIVATE Qt6::Network Qt6::Test)
    add_test(NAME meo-ai.resources COMMAND meo-ai-resource-client-test)

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

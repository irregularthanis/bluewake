cmake_minimum_required(VERSION 3.20)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(bluewake_native_work_pool_tests LANGUAGES C)
    include(CTest)
endif()

get_filename_component(BLUEWAKE_POOL_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)

add_executable(bluewake_native_work_pool_test
    ${BLUEWAKE_POOL_REPO_ROOT}/tests/native_work_pool_test.c
    ${BLUEWAKE_POOL_REPO_ROOT}/cmake/composite/native_work_pool.c)
target_include_directories(bluewake_native_work_pool_test PRIVATE
    ${BLUEWAKE_POOL_REPO_ROOT}/cmake/composite)

if(NOT WIN32)
    find_package(Threads REQUIRED)
    target_link_libraries(bluewake_native_work_pool_test PRIVATE Threads::Threads m)
endif()

add_test(NAME bluewake_native_work_pool_serial_test
    COMMAND bluewake_native_work_pool_test 0)
set_tests_properties(bluewake_native_work_pool_serial_test PROPERTIES
    ENVIRONMENT "BLUEWAKE_NATIVE_WORKERS=invalid"
    LABELS "native-work-pool;fast"
    TIMEOUT 15)

if(NOT WIN32)
    add_test(NAME bluewake_native_work_pool_zero_test
        COMMAND bluewake_native_work_pool_test 0)
    set_tests_properties(bluewake_native_work_pool_zero_test PROPERTIES
        ENVIRONMENT "BLUEWAKE_NATIVE_WORKERS=0"
        LABELS "native-work-pool;fast"
        TIMEOUT 15)

    foreach(BLUEWAKE_POOL_WORKERS IN ITEMS 1 2 3)
        add_test(NAME bluewake_native_work_pool_workers_${BLUEWAKE_POOL_WORKERS}_test
            COMMAND bluewake_native_work_pool_test ${BLUEWAKE_POOL_WORKERS})
        set_tests_properties(bluewake_native_work_pool_workers_${BLUEWAKE_POOL_WORKERS}_test PROPERTIES
            ENVIRONMENT "BLUEWAKE_NATIVE_WORKERS=${BLUEWAKE_POOL_WORKERS}"
            LABELS "native-work-pool;fast"
            TIMEOUT 15)
    endforeach()

    add_test(NAME bluewake_native_work_pool_clamped_test
        COMMAND bluewake_native_work_pool_test 1)
    set_tests_properties(bluewake_native_work_pool_clamped_test PROPERTIES
        ENVIRONMENT "BLUEWAKE_NATIVE_WORKERS=99"
        LABELS "native-work-pool;fast"
        TIMEOUT 15)
endif()

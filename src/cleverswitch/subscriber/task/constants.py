FEATURE_DEVICE_TYPE_AND_NAME_SW_ID = 10
FEATURE_REPROG_CONTROLS_V4_SW_ID = 8
FEATURE_CHANGE_HOST_SW_ID = 9
GET_DEVICE_TYPE_SW_ID = 12
GET_DEVICE_NAME_SW_ID = 13
FIND_ES_CIDS_FLAGS_SW_ID = 11


class Task:
    class Feature:
        class Name:
            CHANGE_HOST = "change-host-feature"
            CID_REPORTING = "cid-reporting-feature"
            NAME_AND_TYPE = "name-and-type-feature"

    class Name:
        FIND_ES_CIDS_FLAGS = "find-es-cids-flags"
        GET_DEVICE_TYPE = "get-device-type"
        GET_DEVICE_NAME = "get-device-name"

from pybrainlife.api.utils import nested_dataclass, hydrate


def test_hydrate():

    def custom_class_fetch(id):
        return CustomClass.normalize({"_id": id, "desc": "test" + id[-1]})

    @hydrate(custom_class_fetch)
    @nested_dataclass
    class CustomClass:
        id: str
        name: str

        @staticmethod
        def normalize(data):
            if isinstance(data, list):
                return [CustomClass.normalize(d) for d in data]
            data["id"] = data["_id"]
            data["name"] = data["desc"]
            del data["_id"]
            del data["desc"]

            return data

    cust = CustomClass("000000000000000000000000")
    assert cust.id == "000000000000000000000000"
    assert cust.name == "test0"

    cust = CustomClass("000000000000000000000001")
    assert cust.id == "000000000000000000000001"
    assert cust.name == "test1"


    def different_class_fetch(id):
        return DifferentClass.normalize({"_id": id, "custom": "000000000000000000000000"})

    @hydrate(different_class_fetch)
    @nested_dataclass
    class DifferentClass:
        id: str
        custom: CustomClass

        @staticmethod
        def normalize(data):
            if isinstance(data, list):
                return [DifferentClass.normalize(d) for d in data]
            data["id"] = data["_id"]
            del data["_id"]
            return data

    diff = DifferentClass("000000000000000000000001")
    assert diff.id == "000000000000000000000001"
    assert diff.custom.id == "000000000000000000000000"
    assert diff.custom.name == "test0"
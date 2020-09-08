from typing import List, Union, Sequence
import copy
from datetime import timedelta
from functools import wraps
from json import loads as parse_json, JSONDecodeError

from flask import current_app
from inflection import pluralize
from numpy import array

from bvp.data import db
from bvp.data.models.assets import Asset
from bvp.data.models.data_sources import DataSource
from bvp.data.models.user import User


def check_access(service_listing, service_name):
    """
    For a given USEF service name (API endpoint) in a service listing,
    return the list of USEF roles that are allowed to access the service.
    """
    return next(
        service["access"]
        for service in service_listing["services"]
        if service["name"] == service_name
    )


def contains_empty_items(groups: List[List[str]]):
    """
    Return True if any of the items in the groups is empty.
    """
    for group in groups:
        for item in group:
            if item == "" or item is None:
                return True
    return False


def parse_as_list(
    connection: Union[Sequence[Union[str, float]], str, float], of_type: type = None
) -> Sequence[Union[str, float, None]]:
    """
    Return a list of connections (or values), even if it's just one connection (or value)
    """
    connections: Sequence[Union[str, float, None]] = []
    if not isinstance(connection, list):
        if of_type is None:
            connections = [connection]  # type: ignore
        else:
            try:
                connections = [of_type(connection)]
            except TypeError:
                connections = [None]
    else:  # key should have been plural
        if of_type is None:
            connections = connection
        else:
            try:
                connections = [of_type(c) for c in connection]
            except TypeError:
                connections = [None]
    return connections


def get_form_from_request(_request) -> Union[dict, None]:
    if _request.method == "GET":
        d = _request.args.to_dict(
            flat=False
        )  # From MultiDict, obtain all values with the same key as a list
        parsed_d = {}
        for k, v_list in d.items():
            parsed_v_list = []
            for v in v_list:
                try:
                    parsed_v = parse_json(v)
                except JSONDecodeError:
                    parsed_v = v
                if isinstance(parsed_v, list):
                    parsed_v_list.extend(parsed_v)
                else:
                    parsed_v_list.append(v)
            if len(parsed_v_list) == 1:  # Flatten single-value lists
                parsed_d[k] = parsed_v_list[0]
            else:
                parsed_d[k] = parsed_v_list
        return parsed_d
    elif _request.method == "POST":
        return _request.get_json(force=True)
    else:
        return None


def append_doc_of(fun):
    def decorator(f):
        if f.__doc__:
            f.__doc__ += fun.__doc__
        else:
            f.__doc__ = fun.__doc__
        return f

    return decorator


def convert_to_15min(
    value_groups: Union[List[List[float]], List[float]], from_resolution: timedelta
) -> Union[List[List[float]], List[float]]:
    """Resample the values (in value groups) to a resolution of 15 minutes, given the original resolution of the values
    (which has to be a multiple of 15 minutes)."""
    if from_resolution % timedelta(minutes=15) == timedelta(hours=0):
        n = from_resolution // timedelta(minutes=15)
        if isinstance(value_groups[0], list):
            value_groups = [
                list(array(value_group).repeat(n)) for value_group in value_groups
            ]
        else:
            value_groups = list(array(value_groups).repeat(n))
    return value_groups


def groups_to_dict(
    connection_groups: List[str],
    value_groups: List[List[str]],
    generic_asset_type_name: str,
    plural_name: str = None,
    groups_name="groups",
) -> dict:
    """Put the connections and values in a dictionary and simplify if groups have identical values and/or if there is
    only one group.

    Examples:

        >> connection_groups = [[1]]
        >> value_groups = [[300, 300, 300]]
        >> response_dict = groups_to_dict(connection_groups, value_groups, "connection")
        >> print(response_dict)
        <<  {
                "connection": 1,
                "values": [300, 300, 300]
            }

        >> connection_groups = [[1], [2]]
        >> value_groups = [[300, 300, 300], [300, 300, 300]]
        >> response_dict = groups_to_dict(connection_groups, value_groups, "connection")
        >> print(response_dict)
        <<  {
                "connections": [1, 2],
                "values": [300, 300, 300]
            }

        >> connection_groups = [[1], [2]]
        >> value_groups = [[300, 300, 300], [400, 400, 400]]
        >> response_dict = groups_to_dict(connection_groups, value_groups, "connection")
        >> print(response_dict)
        <<  {
                "groups": [
                    {
                        "connection": 1,
                        "values": [300, 300, 300]
                    },
                    {
                        "connection": 2,
                        "values": [400, 400, 400]
                    }
                ]
            }
    """

    if plural_name is None:
        plural_name = pluralize(generic_asset_type_name)

    # Simplify groups that have identical values
    value_groups, connection_groups = unique_ever_seen(value_groups, connection_groups)

    # Simplify if there is only one group
    if len(value_groups) == len(connection_groups) == 1:
        if len(connection_groups[0]) == 1:
            return {
                generic_asset_type_name: connection_groups[0][0],
                "values": value_groups[0],
            }
        else:
            return {plural_name: connection_groups[0], "values": value_groups[0]}
    else:
        d: dict = {groups_name: []}
        for connection_group, value_group in zip(connection_groups, value_groups):
            if len(connection_group) == 1:
                d[groups_name].append(
                    {
                        generic_asset_type_name: connection_group[0],
                        "values": value_group,
                    }
                )
            else:
                d[groups_name].append(
                    {plural_name: connection_group, "values": value_group}
                )
        return d


def unique_ever_seen(iterable: Sequence, selector: Sequence):
    """
    Return unique iterable elements with corresponding lists of selector elements, preserving order.

    >>> a, b = unique_ever_seen([[10, 20], [10, 20], [20, 40]], [1, 2, 3])
    >>> print(a)
    [[10, 20], [20, 40]]
    >>> print(b)
    [[1, 2], 3]
    """
    u = []
    s = []
    for iterable_element, selector_element in zip(iterable, selector):
        if iterable_element not in u:
            u.append(iterable_element)
            s.append(selector_element)
        else:
            us = s[u.index(iterable_element)]
            if not isinstance(us, list):
                us = [us]
            us.append(selector_element)
            s[u.index(iterable_element)] = us
    return u, s


def message_replace_name_with_ea(message_with_connections_as_asset_names: dict) -> dict:
    """For each connection in the message specified by a name, replace that name with the correct entity address."""
    message_with_connections_as_eas = copy.deepcopy(
        message_with_connections_as_asset_names
    )
    if "connection" in message_with_connections_as_asset_names:
        message_with_connections_as_eas["connection"] = asset_replace_name_with_id(
            parse_as_list(  # type:ignore
                message_with_connections_as_eas["connection"], of_type=str
            )
        )
    elif "connections" in message_with_connections_as_asset_names:
        message_with_connections_as_eas["connections"] = asset_replace_name_with_id(
            parse_as_list(  # type:ignore
                message_with_connections_as_eas["connections"], of_type=str
            )
        )
    elif "groups" in message_with_connections_as_asset_names:
        for i, group in enumerate(message_with_connections_as_asset_names["groups"]):
            if "connection" in group:
                message_with_connections_as_eas["groups"][i][
                    "connection"
                ] = asset_replace_name_with_id(
                    parse_as_list(group["connection"], of_type=str)  # type:ignore
                )
            elif "connections" in group:
                message_with_connections_as_eas["groups"][i][
                    "connections"
                ] = asset_replace_name_with_id(
                    parse_as_list(group["connections"], of_type=str)  # type:ignore
                )
    return message_with_connections_as_eas


def asset_replace_name_with_id(connections_as_name: List[str]) -> List[str]:
    """Look up the owner and id given the asset name and construct a type 1 USEF entity address."""
    connections_as_ea = []
    for asset_name in connections_as_name:
        asset = Asset.query.filter(Asset.name == asset_name).one_or_none()
        connections_as_ea.append(asset.entity_address)
    return connections_as_ea


def typed_regex_results(match, value_types) -> dict:
    return {
        k: v_type(v) if v is not None else v
        for k, v, v_type in zip_dic(match.groupdict(), value_types)
    }


def zip_dic(*dicts):
    for i in set(dicts[0]).intersection(*dicts[1:]):
        yield (i,) + tuple(d[i] for d in dicts)


class BaseMessage:
    """Set a base message to which extra info can be added by calling the wrapped function with additional string
    arguments. This is a decorator implemented as a class."""

    def __init__(self, base_message=""):
        self.base_message = base_message

    def __call__(self, func):
        @wraps(func)
        def my_logic(*args, **kwargs):
            message = self.base_message
            if args:
                for a in args:
                    message += " %s" % a
            return func(message)

        return my_logic


def get_or_create_user_data_source(user: User) -> DataSource:
    data_source = DataSource.query.filter(DataSource.user == user).one_or_none()
    if not data_source:
        current_app.logger.info("SETTING UP USER AS NEW DATA SOURCE...")
        data_source = DataSource(user=user)
        db.session.add(data_source)
        db.session.flush()  # flush so that we can reference the new object in the current db session
    return data_source

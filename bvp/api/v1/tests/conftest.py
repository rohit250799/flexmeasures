from typing import List

import pytest

from flask_security import SQLAlchemySessionUserDatastore
from flask_security.utils import hash_password

from bvp.data.services.users import create_user


@pytest.fixture(scope="function", autouse=True)
def setup_api_test_data(db):
    """
    Set up data for API v1 tests.
    """
    print("Setting up data for API v1 tests on %s" % db.engine)

    from bvp.data.models.user import User, Role
    from bvp.data.models.assets import Asset, AssetType

    user_datastore = SQLAlchemySessionUserDatastore(db.session, User, Role)

    # Create a test user without a USEF role
    create_user(
        username="test user without roles",
        email="test_user@seita.nl",
        password=hash_password("testtest"),
    )

    # Create 3 test assets for the test_prosumer user
    test_prosumer = user_datastore.find_user(email="test_prosumer@seita.nl")
    test_asset_type = AssetType(name="test-type")
    db.session.add(test_asset_type)
    asset_names = ["CS 1", "CS 2", "CS 3"]
    assets: List[Asset] = []
    for asset_name in asset_names:
        asset = Asset(
            name=asset_name,
            asset_type_name="test-type",
            capacity_in_mw=1,
            latitude=100,
            longitude=100,
            unit="MW",
        )
        asset.owner = test_prosumer
        assets.append(asset)
        db.session.add(asset)

    print("Done setting up data for API v1 tests")

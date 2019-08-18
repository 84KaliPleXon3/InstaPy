import random
import requests
import sqlite3
from datetime import datetime

from .settings import Settings
from .database_engine import get_database
from .like_util import like_image
from .like_util import check_link
from .util import web_address_navigator
from .util import get_state
from .util import set_state


def get_server_endpoint(topic):
    if topic == "fashion":
        return Settings.pods_fashion_server_endpoint
    elif topic == "food":
        return Settings.pods_food_server_endpoint
    elif topic == "travel":
        return Settings.pods_travel_server_endpoint
    elif topic == "sports":
        return Settings.pods_sports_server_endpoint
    elif topic == "entertainment":
        return Settings.pods_entertainment_server_endpoint
    else:
        return Settings.pods_server_endpoint


def get_recent_posts_from_pods(topic, logger):
    """ fetches all recent posts shared with pods """
    params = {"topic": topic}
    r = requests.get(get_server_endpoint(topic) + "/getRecentPostsV1", params=params)
    try:
        logger.info("Downloaded postids from Pod {}:".format(topic))
        if r.status_code == 200:
            logger.info(r.json())
            return r.json()
        else:
            logger.error(r.text)
            return []
    except Exception as err:
        logger.error("Could not get postids from pod {} - {}".format(topic, err))
        return []


def group_posts(posts, logger):
    light_post_ids = []
    normal_post_ids = []
    heavy_post_ids = []

    for postobj in posts:
        try:
            if postobj["mode"] == "light":
                light_post_ids.append(postobj)
            elif postobj["mode"] == "heavy":
                heavy_post_ids.append(postobj)
            else:
                normal_post_ids.append(postobj)
        except Exception as err:
            logger.error(
                "Failed with Error {}, please upgrade your instapy".format(err)
            )
            normal_post_ids.append(postobj)
    return light_post_ids, normal_post_ids, heavy_post_ids


def share_my_post_with_pods(postid, topic, engagement_mode, logger):
    """ share_my_post_with_pod """
    params = {"postid": postid, "topic": topic, "mode": engagement_mode}
    r = requests.get(get_server_endpoint(topic) + "/publishPost", params=params)
    try:
        logger.info("Publishing to Pods {}".format(postid))
        if r.status_code == 200:
            logger.info(r.text)
            return True
        else:
            logger.error(r.text)
            return False
    except Exception as err:
        logger.error(err)
        return False


def share_with_pods_restriction(operation, postid, limit, logger):
    """ Keep track of already shared posts """
    try:
        # get a DB and start a connection
        db, id = get_database()
        conn = sqlite3.connect(db)

        with conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                "SELECT * FROM shareWithPodsRestriction WHERE profile_id=:id_var "
                "AND postid=:name_var",
                {"id_var": id, "name_var": postid},
            )
            data = cur.fetchone()
            share_data = dict(data) if data else None

            if operation == "write":
                if share_data is None:
                    # write a new record
                    cur.execute(
                        "INSERT INTO shareWithPodsRestriction (profile_id, "
                        "postid, times) VALUES (?, ?, ?)",
                        (id, postid, 1),
                    )
                else:
                    # update the existing record
                    share_data["times"] += 1
                    sql = (
                        "UPDATE shareWithPodsRestriction set times = ? WHERE "
                        "profile_id=? AND postid = ?"
                    )
                    cur.execute(sql, (share_data["times"], id, postid))

                # commit the latest changes
                conn.commit()

            elif operation == "read":
                if share_data is None:
                    return False

                elif share_data["times"] < limit:
                    return False

                else:
                    exceed_msg = "" if share_data["times"] == limit else "more than "
                    logger.info(
                        "---> {} has already been shared with pods {}{} times".format(
                            postid, exceed_msg, str(limit)
                        )
                    )
                    return True

    except Exception as exc:
        logger.error(
            "Dap! Error occurred with share Restriction:\n\t{}".format(
                str(exc).encode("utf-8")
            )
        )

    finally:
        if conn:
            # close the open connection
            conn.close()


def comment_restriction(operation, postid, limit, logger):
    """ Keep track of already shared posts """
    try:
        # get a DB and start a connection
        db, id = get_database()
        conn = sqlite3.connect(db)

        with conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                "SELECT * FROM commentRestriction WHERE profile_id=:id_var "
                "AND postid=:name_var",
                {"id_var": id, "name_var": postid},
            )
            data = cur.fetchone()
            share_data = dict(data) if data else None

            if operation == "write":
                if share_data is None:
                    # write a new record
                    cur.execute(
                        "INSERT INTO commentRestriction (profile_id, "
                        "postid, times) VALUES (?, ?, ?)",
                        (id, postid, 1),
                    )
                else:
                    # update the existing record
                    share_data["times"] += 1
                    sql = (
                        "UPDATE commentRestriction set times = ? WHERE "
                        "profile_id=? AND postid = ?"
                    )
                    cur.execute(sql, (share_data["times"], id, postid))

                # commit the latest changes
                conn.commit()

            elif operation == "read":
                if share_data is None:
                    return False

                elif share_data["times"] < limit:
                    return False

                else:
                    exceed_msg = "" if share_data["times"] == limit else "more than "
                    logger.info(
                        "---> {} has been commented on {}{} times".format(
                            postid, exceed_msg, str(limit)
                        )
                    )
                    return True

    except Exception as exc:
        logger.error(
            "Dap! Error occurred with comment Restriction:\n\t{}".format(
                str(exc).encode("utf-8")
            )
        )

    finally:
        if conn:
            # close the open connection
            conn.close()


# def engage_with_posts(browser, pod_posts):
def engage_with_posts(
    browser,
    pod_posts,
    blacklist,
    username,
    dont_like,
    mandatory_words,
    mandatory_language,
    is_mandatory_character,
    mandatory_character,
    check_character_set,
    ignore_if_contains,
    logger,
    logfolder
):
    liked_img = 0

    for pod_post in pod_posts:
        if (not check_pods_interaction_daily_limit(logfolder, logger)):
            return False
        try:
            pod_post_id = pod_post["postid"]
            post_link = "https://www.instagram.com/p/{}".format(pod_post_id)
            web_address_navigator(browser, post_link)

            inappropriate, user_name, is_video, reason, scope = check_link(
                browser,
                post_link,  # ok
                dont_like,
                mandatory_words,
                mandatory_language,
                is_mandatory_character,
                mandatory_character,
                check_character_set,
                ignore_if_contains,
                logger,
            )

            if not inappropriate and user_name != username:
                like_state, msg = like_image(
                    browser,
                    user_name,
                    blacklist,
                    logger,
                    logfolder,
                    liked_img,
                )

                if like_state is True:
                    # increase pods daily interaction
                    add_one_pod_daily_interaction(logfolder, logger)
                    liked_img += 1

                elif msg == "block on likes":
                    break

        except Exception as err:
            logger.error("Failed for {} with Error {}".format(pod_post, err))


def check_pods_interaction_daily_limit(logfolder, logger):
    """ Check if its possible to like posts based on daily restrictions """
    today = datetime.now().strftime("%Y-%m-%d")
    # get current state
    state = get_state(logfolder, logger)
    pods_last_interaction_day = ''
    try:
        pods_last_interaction_day = state['pods']['pods_last_interaction_day']
        pods_daily_interaction_count = state['pods']['pods_daily_interaction_count']
    except KeyError:
        pass

    # new data and there no interactions made for this day
    if (pods_last_interaction_day == '' or pods_last_interaction_day != today):
        # set_state()
        state['pods'] = {
            'pods_last_interaction_day': today, 'pods_daily_interaction_count': 0
        }
        # update state
        set_state(logfolder, logger, state)
        return True
    elif (pods_last_interaction_day == today and pods_daily_interaction_count < Settings.pods_daily_interaction_limit):
        return True
    else:
        # limit reached, do not like it!
        logger.info('Daily interaction limit ({}) with posts from Pod reached! Skipping liking Posts from Pod today.'.format(Settings.pods_daily_interaction_limit))
        return False


def add_one_pod_daily_interaction(logfolder, logger):
    """ Increase Pod Daily Interaction """
    state = get_state(logfolder, logger)
    try:
        pods_daily_interaction_count = state['pods']['pods_daily_interaction_count']
        pods_daily_interaction_count += 1
        state['pods'] = {
                'pods_last_interaction_day': state['pods']['pods_last_interaction_day'],
                'pods_daily_interaction_count': pods_daily_interaction_count
        }
        set_state(logfolder, logger, state)
    except KeyError:
        logger.warn('Unable to update pod daily interaction count')

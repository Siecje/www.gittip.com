"""Wireup
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os

import aspen
import balanced
import gittip
import raven
import mandrill
from environment import Environment, is_yesish
from gittip.elsewhere import PlatformRegistry
from gittip.elsewhere.bitbucket import Bitbucket
from gittip.elsewhere.bountysource import Bountysource
from gittip.elsewhere.github import GitHub
from gittip.elsewhere.openstreetmap import OpenStreetMap
from gittip.elsewhere.twitter import Twitter
from gittip.elsewhere.venmo import Venmo
from gittip.models.account_elsewhere import AccountElsewhere
from gittip.models.community import Community
from gittip.models.participant import Participant
from gittip.models.email_address_with_confirmation import EmailAddressWithConfirmation
from gittip.models import GittipDB


def canonical(env):
    gittip.canonical_scheme = env.canonical_scheme
    gittip.canonical_host = env.canonical_host


def db(env):
    dburl = env.database_url
    maxconn = env.database_maxconn
    db = GittipDB(dburl, maxconn=maxconn)

    db.register_model(Community)
    db.register_model(AccountElsewhere)
    db.register_model(Participant)
    db.register_model(EmailAddressWithConfirmation)

    return db

def mail(env):
    mandrill_client = mandrill.Mandrill(env.mandrill_key)

    return mandrill_client

def billing(env):
    balanced.configure(env.balanced_api_secret)


def username_restrictions(website):
    if not hasattr(gittip, 'RESTRICTED_USERNAMES'):
        gittip.RESTRICTED_USERNAMES = os.listdir(website.www_root)


def make_sentry_teller(env):
    if not env.sentry_dsn:
        aspen.log_dammit("Won't log to Sentry (SENTRY_DSN is empty).")
        def noop(exception, request=None):
            pass
        return noop

    sentry = raven.Client(env.sentry_dsn)

    def tell_sentry(exception, request=None):

        # Decide if we care.
        # ==================

        if isinstance(exception, aspen.Response):

            if exception.code < 500:

                # Only log server errors to Sentry. For responses < 500 we use
                # stream-/line-based access logging. See discussion on:

                # https://github.com/gittip/www.gittip.com/pull/1560.

                return


        # Find a user.
        # ============
        # | is disallowed in usernames, so we can use it here to indicate
        # situations in which we can't get a username.

        request_context = getattr(request, 'context', None)
        user = {}
        user_id = 'n/a'
        if request_context is None:
            username = '| no context'
        else:
            user = request.context.get('user', None)
            if user is None:
                username = '| no user'
            else:
                is_anon = getattr(user, 'ANON', None)
                if is_anon is None:
                    username = '| no ANON'
                elif is_anon:
                    username = '| anonymous'
                else:
                    participant = getattr(user, 'participant', None)
                    if participant is None:
                        username = '| no participant'
                    else:
                        username = getattr(user.participant, 'username', None)
                        if username is None:
                            username = '| no username'
                        else:
                            user_id = user.participant.id
                            username = username.encode('utf8')
                            user = { 'id': user_id
                                   , 'is_admin': user.participant.is_admin
                                   , 'is_suspicious': user.participant.is_suspicious
                                   , 'claimed_time': user.participant.claimed_time.isoformat()
                                   , 'url': 'https://www.gittip.com/{}/'.format(username)
                                    }


        # Fire off a Sentry call.
        # =======================

        tags = { 'username': username
               , 'user_id': user_id
                }
        extra = { 'filepath': getattr(request, 'fs', None)
                , 'request': str(request).splitlines()
                , 'user': user
                 }
        result = sentry.captureException(tags=tags, extra=extra)


        # Emit a reference string to stdout.
        # ==================================

        ident = sentry.get_ident(result)
        aspen.log_dammit('Exception reference: ' + ident)

    return tell_sentry


def nanswers(env):
    from gittip.models import participant
    participant.NANSWERS_THRESHOLD = env.nanswers_threshold


class BadEnvironment(SystemExit):
    pass


def accounts_elsewhere(website, env):

    twitter = Twitter(
        website.asset_url,
        env.twitter_consumer_key,
        env.twitter_consumer_secret,
        env.twitter_callback,
    )
    github = GitHub(
        website.asset_url,
        env.github_client_id,
        env.github_client_secret,
        env.github_callback,
    )
    bitbucket = Bitbucket(
        website.asset_url,
        env.bitbucket_consumer_key,
        env.bitbucket_consumer_secret,
        env.bitbucket_callback,
    )
    openstreetmap = OpenStreetMap(
        website.asset_url,
        env.openstreetmap_consumer_key,
        env.openstreetmap_consumer_secret,
        env.openstreetmap_callback,
        env.openstreetmap_api_url,
        env.openstreetmap_auth_url,
    )
    bountysource = Bountysource(
        website.asset_url,
        None,
        env.bountysource_api_secret,
        env.bountysource_callback,
        env.bountysource_api_host,
        env.bountysource_www_host,
    )
    venmo = Venmo(
        website.asset_url,
        env.venmo_client_id,
        env.venmo_client_secret,
        env.venmo_callback,
    )

    signin_platforms = [twitter, github, bitbucket, openstreetmap]
    website.signin_platforms = PlatformRegistry(signin_platforms)
    AccountElsewhere.signin_platforms_names = tuple(p.name for p in signin_platforms)

    # For displaying "Connected Accounts"
    website.social_profiles = [twitter, github, bitbucket, openstreetmap, bountysource]

    all_platforms = signin_platforms + [bountysource, venmo]
    website.platforms = AccountElsewhere.platforms = PlatformRegistry(all_platforms)


def other_stuff(website, env):
    website.asset_url = env.gittip_asset_url.replace('%version', website.version)
    website.cache_static = env.gittip_cache_static
    website.compress_assets = env.gittip_compress_assets

    website.segment_key = env.segment_key
    website.sentry_dsn = env.sentry_dsn

    website.log_metrics = env.log_metrics


def env():
    env = Environment(
        DATABASE_URL                    = unicode,
        CANONICAL_HOST                  = unicode,
        CANONICAL_SCHEME                = unicode,
        DATABASE_MAXCONN                = int,
        GITTIP_ASSET_URL                = unicode,
        GITTIP_CACHE_STATIC             = is_yesish,
        GITTIP_COMPRESS_ASSETS          = is_yesish,
        BALANCED_API_SECRET             = unicode,
        #DEBUG                           = unicode,
        GITHUB_CLIENT_ID                = unicode,
        GITHUB_CLIENT_SECRET            = unicode,
        GITHUB_CALLBACK                 = unicode,
        BITBUCKET_CONSUMER_KEY          = unicode,
        BITBUCKET_CONSUMER_SECRET       = unicode,
        BITBUCKET_CALLBACK              = unicode,
        TWITTER_CONSUMER_KEY            = unicode,
        TWITTER_CONSUMER_SECRET         = unicode,
        TWITTER_CALLBACK                = unicode,
        BOUNTYSOURCE_API_SECRET         = unicode,
        BOUNTYSOURCE_CALLBACK           = unicode,
        BOUNTYSOURCE_API_HOST           = unicode,
        BOUNTYSOURCE_WWW_HOST           = unicode,
        VENMO_CLIENT_ID                 = unicode,
        VENMO_CLIENT_SECRET             = unicode,
        VENMO_CALLBACK                  = unicode,
        OPENSTREETMAP_CONSUMER_KEY      = unicode,
        OPENSTREETMAP_CONSUMER_SECRET   = unicode,
        OPENSTREETMAP_CALLBACK          = unicode,
        OPENSTREETMAP_API_URL           = unicode,
        OPENSTREETMAP_AUTH_URL          = unicode,
        NANSWERS_THRESHOLD              = int,
        UPDATE_GLOBAL_STATS_EVERY       = int,
        CHECK_DB_EVERY                  = int,
        SEGMENT_KEY                     = unicode,
        SENTRY_DSN                      = unicode,
        LOG_METRICS                     = is_yesish,
        MANDRILL_KEY                    = unicode,
        RAISE_CARD_EXPIRATION           = is_yesish,

        # This is used in our Procfile. (PORT is also used but is provided by
        # Heroku; we don't set it ourselves in our app config.)
        GUNICORN_OPTS                   = unicode,
    )


    # Error Checking
    # ==============

    if env.malformed:
        these = len(env.malformed) != 1 and 'these' or 'this'
        plural = len(env.malformed) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit( "Oh no! Gittip.com couldn't understand %s " % these
                        , "environment variable%s:" % plural
                         )
        aspen.log_dammit(" ")
        for key, err in env.malformed:
            aspen.log_dammit("  {} ({})".format(key, err))
        aspen.log_dammit(" ")
        aspen.log_dammit("See ./default_local.env for hints.")

        aspen.log_dammit("=" * 42)
        keys = ', '.join([key for key in env.malformed])
        raise BadEnvironment("Malformed envvar{}: {}.".format(plural, keys))

    if env.missing:
        these = len(env.missing) != 1 and 'these' or 'this'
        plural = len(env.missing) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit( "Oh no! Gittip.com needs %s missing " % these
                        , "environment variable%s:" % plural
                         )
        aspen.log_dammit(" ")
        for key in env.missing:
            aspen.log_dammit("  " + key)
        aspen.log_dammit(" ")
        aspen.log_dammit( "(Sorry, we must've started looking for "
                        , "%s since you last updated Gittip!)" % these
                         )
        aspen.log_dammit(" ")
        aspen.log_dammit("Running Gittip locally? Edit ./local.env.")
        aspen.log_dammit("Running the test suite? Edit ./tests/env.")
        aspen.log_dammit(" ")
        aspen.log_dammit("See ./default_local.env for hints.")

        aspen.log_dammit("=" * 42)
        keys = ', '.join([key for key in env.missing])
        raise BadEnvironment("Missing envvar{}: {}.".format(plural, keys))

    return env


if __name__ == '__main__':
    env()

## Mod Democracy Bot v1.0 by u/BuckRowdy

##  Setup for the bot is as follows:
##  Set up your config.json file with sub specific variables. 
##  Create three wiki pages on your sub.  Suggest creating a folder system such as:
##  wiki page for the ban list so that all mods can view easier - r/subreddit/wiki/democracy_bot/dump_list 
##  wiki page for the cooldown list.  r/subreddit/wiki/democracy_bot/lock_list
##  wiki page for the user scoreboard. r/subreddit/wiki/democracy_bot/user_scores
##  In config.json, the submission list is any post you wish to remain in the sticky spot, in case of important announcements.
##  Create four flair classes, more information in am_config.yaml
##  Bot consists of four files, democracy_bot.py, prod_config.json, ph_config.py (logging config) and am_config.yaml (corresponding automod rules.), and a .env file with your login credentials for the bot. 



import praw
import os
from datetime import datetime, timedelta
# Idk what happened, the bot was throwing a weird error until I imported time as another variable, computers are weird.
import time as slumber
from praw.models import Message
import re
import random
import json
import nltk
from nltk.corpus import wordnet
import prawcore.exceptions
import os
from dotenv import load_dotenv
from ph_config import setup_logger


script_name = os.path.splitext(os.path.basename(__file__))[0]
logger = setup_logger(script_name)

# Load secrets from .env
load_dotenv()

# Get the current environment ('prod' or 'test')
env = os.getenv('ENV')

# Choose the appropriate config file
config_file = '/home/blackie/bots/ph/prod_config.json' if env == 'prod' else '/home/blackie/bots/ph/test_config.json'

# Load the config file
with open(config_file, 'r') as f:
	config = json.load(f)


# Reddit application information
# Credentials stored in an .env file.
reddit = praw.Reddit(
	client_id=os.getenv('CLIENT_ID'),
	client_secret=os.getenv('CLIENT_SECRET'),
	username=os.getenv('BOT_USERNAME'),
	password=os.getenv('BOT_PASSWORD'),
	user_agent="subreddit_moderation_democratization_tool for r_politicalhumor by u/BuckRowdy"
)

logger.info(f'Logged in as {reddit.user.me()}...')



# Import variables from prod_config.json

# List of names of people to randomly commment, X is a little piss baby. Add names as needed.
PISS_BABIES = config['piss_babies']
# Flair class "levels".  When used in conjunction with automod sub level karma rules you can set "permission" levels for mod actions.
MOD_PERMS_FLAIR_CLASSES = config["mod_perms_flair_class"]  
RESTORE_FLAIR_CLASSES = config["restore_flair_classes"] 
REMOVE_FLAIR_CLASSES = config["flair_classes_remove"] 
FULL_PERMS_FLAIR_CLASSES = config["full_perms_flair"]
# Define how long the bot will sleep for.
SLEEP_SECONDS = config['bot_sleep_seconds']
# Define wiki pages for data storage visible to all mods. 
BAN_LIST_WIKI_PAGE = config["ban_list_wiki_page"]
USER_SCOREBOARD_WIKI_PAGE = config["user_scoreboard_wiki_page"]
COOLDOWN_LIST_WIKI_PAGE = config["cooldown_list_wiki_page"]
BOT_ACCOUNT_NAME = config["bot_account_name"]
MOD_HARASSMENT_REPLY_LIST = config["mod_harassment_reply_list"]
MOD_HARASSMENT_FOOTER = config["mod_harassment_footer"]
# Unlock submissions that are locked with more than 25 karma.
UNLOCK_KARMA_LIMIT = config['unlock_karma_limit']
# Bans users of posts with a downvote/upvote limtit of 0.39
SUBMISSION_VOTE_RATIO_BAN_LIMIT = config['submission_vote_ratio_ban_limit']
SUBMISSION_VOTE_RATIO_BAN_DURATION = config['submission_vote_ratio_ban_duration']
# Users will be banned when their comment karma is below this value.
COMMENT_KARMA_BAN_FLOOR = config['comment_karma_ban_floor']
COMMENT_BAN_DURATION_DAYS = config['comment_ban_duration_days']
# Set a cooldown period of 2 minutes so users don't spam lock threads.
LOCK_COMMAND_COOLDOWN = timedelta(minutes=config['lock_cooldown_minutes'])
STICKY_COMMENT_UNLOCK_KARMA_THRESHOLD = config['sticky_comment_unlock']


def get_ban_message(subreddit_name, ban_type):
	"""
	Retrieves a ban message for a specific subreddit.
	"""
	if not config:
		return ''
	
	subreddit_config = config.get('subreddits', {}).get(subreddit_name, {})
	subreddit_name = subreddit_config.get('name', '')
	
	if ban_type == "comment_karma":
		return subreddit_config.get('ban_message', '')
	elif ban_type == "ban_command":
		return subreddit_config.get('ban_command_ban_message', '')
	else:
		return ''


def get_banlist(subreddit):
	"""
	Keep a log of users and timestamps in a wiki page.  Users will fall off the list after a day.
	"""

	banlist = {}
	try:
		content = subreddit.wiki[f'{BAN_LIST_WIKI_PAGE}'].content_md
	except Exception as e:
		logger.error(f"Failed to fetch banout/dumplist for {subreddit.display_name} with exception {e}")
		return banlist

	if not content:
		return banlist

	for line in content.split('\n'):
		name, time = line.split(',')
		try:
			banlist[name] = datetime.strptime(time.strip(), "%Y-%m-%d %H:%M:%S")  # strip whitespace from time
		except ValueError as ve:
			logger.error(f'Error parsing time from banlist for user {name}: {ve}')
	return banlist


def add_to_banlist(subreddit, name):
	"""
	Add names and timestamps to a subreddit wiki log so all mods can view it.
	"""
	banlist = get_banlist(subreddit)
	banlist[name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	content = '\n'.join([f'{k},{v}' for k, v in banlist.items()])
	try:
		subreddit.wiki[f'{BAN_LIST_WIKI_PAGE}'].edit(content=content)
	except Exception as e:
		logger.error(f"Failed to add {name} to {subreddit.display_name} banlist with exception {e}")


def remove_from_banlist(subreddit, name) -> None:
	"""Removes names of banned users from the wiki page log.
	"""
	banlist = get_banlist(subreddit)
	if name in banlist:
		del banlist[name]
		content = '\n'.join([f'{k},{v}' for k, v in banlist.items()])
		try:
			subreddit.wiki[f'{BAN_LIST_WIKI_PAGE}'].edit(content=content)
		except Exception as e:
			logger.error(f"Failed to remove {name} from {subreddit.display_name} with exception {e}")


def unlock_submission(submission):
	"""
	Unlocks a specific submission
	"""
	try:
		# Master condition: unlock any post with score of 25 or more so that other commands work.
		# Set karma level where desired.
		submission_score = submission.score
		submission_is_locked = submission.locked
	except Exception as e:
		logger.error(f"Failed to retrieve submission score or locked status for submission id {submission.id} while trying to lock submission.")
		return

	if submission_is_locked and submission_score >= UNLOCK_KARMA_LIMIT:
		try:
			submission.mod.unlock()
		except Exception as e:
			logger.error(f"Failed to unlock submission id {submission.id} with exception e")
		logger.info(f"Unlocking Submission: {submission.id} on r/{submission.subreddit}")


def unlock_comments(submission):
	"""
	Unlocks comments from submission
	"""

	try:
		submission.comments.replace_more()
	except Exception as e:
		logger.error(f"Failed to fetch all comments for submission id {submission.id} with error {e} while unlocking comments")
		return
	# Make a list of comments
	try:
		comments = submission.comments.list()
	except Exception as e:
		logger.error(f"Failed to make list of comments for submission id {submission.id} with exception {e} while unlocking comments")
		return

	# Do nothing if we have no comments
	if not comments or len(comments) == 0:
		return

	# Look for stickied comment on the thread.
	stickied_comment = next((comment for comment in comments if comment.stickied), None)

	# Check if a stickied comment is present on the thread.
	if not stickied_comment:
		return
	elif stickied_comment.author.name == f"{BOT_ACCOUNT_NAME}" and not submission.stickied:
		stickied_comment.mod.undistinguish()
		stickied_comment.mod.remove()
		logger.info(f"Unstickied and removed comment {stickied_comment.id} on post {submission.title} by u/{BOT_ACCOUNT_NAME} in r/{submission.subreddit}")
	elif stickied_comment.score >= STICKY_COMMENT_UNLOCK_KARMA_THRESHOLD and submission.locked:
		# If there's a sticky thread is it locked and does it have a score of 10 or more?  If so, unlock.:
		submission.mod.unlock()
		logger.info(
			f"Unlocked comments for submission {submission.id} in r/{submission.subreddit} due to {stickied_comment.author}'s comment with {STICKY_COMMENT_UNLOCK_KARMA_THRESHOLD} upvotes.")
	return


def handle_poor_karma_submissions(submission, subreddit):
	"""
	Actions to take on submissions with poor karma
	"""
	banlist = get_banlist(subreddit)
	# Check if a post has an upvote ratio of 40% or more and if the post author is already banned.
	try:
		submission_upvote_ratio = submission.upvote_ratio
		submission_author_name = submission.author.name
	except Exception as e:
		logger.error(f"Failed to retrieve upvote ratio or author name for submission id {submission.id} while handling poor karma submission.")
		return

	if submission_upvote_ratio <= SUBMISSION_VOTE_RATIO_BAN_LIMIT and submission_author_name not in banlist:
		# Ban user for one day with ban message generated on per sub basis.
		ban_message = get_ban_message("politicalhumor", ban_type= "comment_karma")
		ban_user(subreddit,
				 submission.author,
				 SUBMISSION_VOTE_RATIO_BAN_DURATION,
				 ban_reason = f"{submission.permalink}",
				 ban_message=f"{ban_message}")

		# Add banned user to wiki banned log giving all mods quick access to the list of event banned users.
		add_to_banlist(subreddit, submission.author.name)
		logger.info(
			f'Banned user {submission.author} for negative post score {submission.score} in {subreddit.display_name}.')


def check_submissions(subreddit):
	"""
	Check posts for comment score ban attempt.
	Fetch the banlist to check recently banned users
	"""
	logger.info(f'Checking submissions for subreddit {subreddit.display_name}')
	# Check 100 posts, the bot runs every 3-4 minnutes, 100 should be enough to catch current activity.
	try:
		new_submissions = subreddit.new(limit=100)
	except Exception as e:
		logger.error(f"Failed to retrieve submissions from {subreddit.display_name} with error {e}")
		return

	for submission in new_submissions:
		unlock_submission(submission)
		unlock_comments(submission)
		handle_poor_karma_submissions(submission, subreddit)


def ban_user(subreddit, author, duration, ban_reason, ban_message):
	"""Bans a user from reddit"""
	try:
		subreddit.banned.add(author, duration=duration, ban_reason=ban_reason,
							 ban_message=f"{ban_message}")
		#logger.info(f'Banned user {author} in r/{subreddit.display_name} for {duration}.')
		# Add to banlist after successful ban
		add_to_banlist(subreddit, author.name)
	except prawcore.exceptions.NotFound as e:
		# ShadowBanned
		logger.error(f"Error: {e}, Author: {author}, Comment ID: {comment.id}")	
	except prawcore.exceptions.Forbidden as e:
		# Suspended
		logger.error(f"Error: {e}, Author: {author}, Comment ID: {comment.id}")
	except prawcore.exceptions.ServerError as e:
		logger.error(f"Error - A Reddit server error occurred. Sleeping 3 min before trying again...\n\t{e}")
		time.sleep(180)
		pass
	except Exception as e:
		logger.error(f"Error - An error occurred: [{e}]")


def decode_crt():
	nltk.download('wordnet')  # Download WordNet corpus
	logger.info("Now finding CRT words.")
	# Get lemmas for common nouns starting with C, R, and T
	c_words = set()
	r_words = set()
	t_words = set()

	for synset in wordnet.all_synsets(pos='n'):
		for lemma in synset.lemmas():
			if lemma.name().startswith('c') or lemma.name().startswith('C'):
				c_words.add(lemma.name())
			elif lemma.name().startswith('r') or lemma.name().startswith('R'):
				r_words.add(lemma.name())
			elif lemma.name().startswith('t') or lemma.name().startswith('T'):
				t_words.add(lemma.name())

	# Choose a random word for C, R, and T
	random_c_word = random.choice(list(c_words))
	random_r_word = random.choice(list(r_words))
	random_t_word = random.choice(list(t_words))

	return f"I have no idea what CRT is. Is it...\n\nC: {random_c_word}\n\nR: {random_r_word}\n\nT: {random_t_word}\n\n---\n\n[^(What in the world is this?)](https://www.reddit.com/r/PoliticalHumor/comments/14fpdyl/announcing_updated_moderator_permissions_for_all/)"



def check_comments(subreddit):
	"""
	Looks at comments in a subreddit and does applicable actions
	"""
	# Check comments for lots of comment check conditions.
	logger.info(f'Checking comments for {subreddit.display_name}')
	# Check lots of comments.
	try:
		subreddit_comments = subreddit.comments(limit=1000)
	except Exception as e:
		logger.error(f"Failed to retrieve comments from {subreddit.display_name} with exception {e}")
		return
	for comment in subreddit_comments:
		author_name = comment.author.name
		try:
			# Reddit's save function gives a quick and dirty basic boolean database.
			if comment.saved or comment.banned_by:
				continue
			# Ban user if comment is below the ban floor and they're not on the list already.
			if comment.score <= COMMENT_KARMA_BAN_FLOOR and author_name not in get_banlist(subreddit) and author_name != "AutoModerator":
				# Temporarily ban the user
				ban_message=get_ban_message("politicalhumor", ban_type="comment_karma")
				ban_user(comment.subreddit, comment.author, COMMENT_BAN_DURATION_DAYS, ban_reason=f"{comment.permalink}", ban_message=f"{ban_message}")
				# Comment.save() is called to keep from removing every comment on the thread.
				comment.save()
				logger.info("Saving comment.")
			# Check for comment commands
			handle_comment_commands(comment, subreddit)
		except Exception as e:
			logger.error(f'Error in processing comment: {e}')


def unlock_comments_and_approve(subreddit_name):
	"""
	Unlocks and approves submissions on the subreddit_submission_list
	"""
	# Unlock and approve announcement posts or posts you want to stay static and pinned.
	subreddit_submission_list = config.get('subreddits', {}).get(subreddit_name, {}).get('submission_list', [])
	if not subreddit_submission_list:
		return

	for submission_id in subreddit_submission_list:
		try:
			submission = reddit.submission(id=submission_id)
		except Exception as e:
			logger.error(f"Failed to fetch submission {submission_id} while unlocking comments")
			return

		if submission.banned_by:  # check if the submission is removed, via the !remove command
			try:
				submission.mod.approve()  # approve the submission
				logger.info(f"Approving removed submission: {submission.title} in r{submission.subreddit}")
				submission.mod.sticky(bottom=True)
				logger.info(f'Approved removed submission {submission.id} in r/{submission.subreddit}')
			except Exception as e:
				logger.error(f"Failed to approve submission {submission} with exception {e}")
		# Unlock and sticky the post, define in submission IDs list above.
		if submission.locked:
			try:
				submission.mod.unlock()
				if not submission.stickied:
					submission.mod.sticky(bottom=True)
				logger.info(f'Unlocked comments for submission {submission} in r/{submission.subreddit}')
			except Exception as e:
				logger.error(f'Error in unlocking comments: {e} for {submission}')


def handle_comment_commands(comment, subreddit):
	"""Main function for handlings all !* commands that users can type in comments"""
	logger.debug(f"Handling comment commands for comment {comment} on {subreddit}")
	handle_ban_command(comment)
	handle_lock_command(comment)        
	handle_unlock_command(comment) 
	handle_remove_command(comment) 
	handle_restore_command(comment) 
	handle_sticky_command(comment)
	handle_piss_command(comment) 
	handle_leaderboard_command(comment)
	handle_crt_command(comment) 
	handle_modlog_command(comment) 
	handle_harassment_command(comment) 


def handle_lock_command(comment):
	"""Does actions after finding !lock in a comment. """
	# Check for lock keyword and that comment is not a top level comment

	## TODO: sticky a comment when a user-mod locks a thread.
	if not re.match(r"! ?[Ll]ock", comment.body):
		return
	if comment.is_root:
		return
		
	author_name = comment.author.name
	# Get the list of users on the cooldown list.
	lock_list = get_lock_list(comment.subreddit)
	if author_name in lock_list:
		# Check is user needs a cooldown
		time_since_last_command = datetime.now() - lock_list[author_name]
		if time_since_last_command < LOCK_COMMAND_COOLDOWN:
			logger.info(
				f"User {author_name} is spamming !lock command in {comment.subreddit}, ignoring this command.")
			return
	# Fetch the id of the comment to be locked via keyword
	try:
		parent_comment = reddit.comment(id=comment.parent_id.split('_')[1])
		# Some r/redditdev threads indicated comment.refresh() needs to be called. It works, so I guess they were right.
		parent_comment.refresh()
	except Exception as e:
		logger.error(f"Failed to get parent comment for {comment} with exception {e} while handling lock command for same comment")
		return

	# If the comment is already locked, save the !lock comment so it can't be used again.
	if parent_comment.locked:
		logger.info(f"Parent comment {comment.id} already locked in {comment.subreddit}, passing. ")
		logger.info(f"Saving !lock comment. {comment}")
		try:
			comment.save()
		except Exception as e:
			logger.error(f"Failed to save comment {comment} with error {e}")

	else:
		# If comment not locked, lock it.
		try:
			parent_comment.mod.lock()  # lock the parent comment
			update_user_scores(comment)
		except Exception as e:
			logger.error(f"Failed to lock parent comment of {comment} while handling lock command with error {e}")
			comment.reply(f"I couldn't lock this comment due to error: [{e}]")
		logger.info(
			f'Locked the parent comment {parent_comment.id} in r/{comment.subreddit} due to a "!lock" command.')
		# Add the user to the lock list wiki page for cooldown restriction.
		update_lock_list(comment.subreddit, author_name, datetime.now())
		# Remove the !lock comment
		try:
			comment.save()
		except Exception as e:
			logger.error(f"Failed to save comment {comment} with error {e}")

		logger.info(f"Saved !lock comment in r/{comment.subreddit} so it won't be used again.")


def handle_unlock_command(comment):
	"""Does actions after finding !unlock in a commment"""
	# Unlock the grandparent comment since you cannot reply to it directly.
	if not re.match(r"! ?[Uu]nlock", comment.body):
		return
   
	elif comment.is_root:
		unlock_command_submission(comment)
		comment.save()    
	else:
		try:
			parent_comment = reddit.comment(id=comment.parent_id.split('_')[1])
			parent_comment.refresh()
			try:
				grandparent_comment = parent_comment.parent()
			except Exception as e:
				logger.error(F"Couldn't get the grandparent comment.")	
			grandparent_comment.refresh()
			
			if not grandparent_comment.locked:
				logger.info(
					f"Comment {grandparent_comment.id} in r/{comment.subreddit} already unlocked, passing. ")
				try:
					comment.save()
				except Exception as e:
					logger.error(f"Could not save comment: [{e}]")	
				logger.info("Saving comment...")
			else:
				try:
					grandparent_comment.mod.unlock()  # unlock the grandparent comment
					update_user_scores(comment)
				except Exception as e:
					logger.error(f"Couldn't unlock comment: {comment.id} due to [{e}]")
				logger.info(
					f"Unlocked the grandparent comment {grandparent_comment.id} in r/{comment.subreddit} due to an !unlock command.")
				try:
					comment.reply(f"You successfully unlocked [this comment.]({grandparent_comment.permalink})")
					comment.save()
				except Exception as e:
					logger.error(f"Couldn't save or reply to comment because of [{e}]")
				logger.info(f"Saved !unlock comment.")
		except AttributeError:
			logger.error("Could not unlock: parent comment is a top-level comment.")
		except Exception as e:
			logger.error(f"An error occurred while trying to unlock: {e}")

def unlock_command_submission(comment):
	try:
		submission = reddit.submission(id=comment.link_id.split('_')[1])
		submission.comments.replace_more(limit=None)
	except Exception as e:
	   logger.error(f"An error occurred while trying to unlock submission: {e}")	
	comment_unlock_count = 0
	for comment in submission.comments.list():
		if comment.locked:
			comment.mod.unlock()
			comment_unlock_count +=1
	logger.info(f"Unlocked {comment_unlock_count} comments in r/{comment.subreddit} due to an !unlock command.")
	comment.reply(f"You have successfully unlocked {comment_unlock_count} comments.")	


def handle_remove_command(comment):
	"""Does actions after finding !remove in a comment."""
	if not re.match(r"! ?[Rr]emove", comment.body):
		return
	author = comment.author
	# Karma restriction check for !remove command
	flair = next(reddit.subreddit(f"{comment.subreddit}").flair(redditor=author))
	if not flair['flair_css_class'] in REMOVE_FLAIR_CLASSES:
		comment.reply(f"u/{comment.author}, I'm sorry you don't have the proper permissions. Level up by commenting more.")
		comment.save()
		return None

	if not comment.is_root or comment.banned_by:  # if the comment is not top-level
		try:
			parent_comment = reddit.comment(id=comment.parent_id.split('_')[1])
			parent_comment.mod.remove()  # remove the parent comment
		except Exception as e:
			logger.error(f"Failed to retrieve parent comment for {comment} with error {e}")
			return
		logger.info(f'Removed the parent comment {parent_comment.id} due to a "!remove" command.')

	else:  # if the comment is top-level, remove the submission
		try:
			submission = reddit.submission(id=comment.link_id.split('_')[1])
		except Exception as e:
			logger.error(f"Failed to retrieve submission for comment {comment} with error {e}")
			return

		if not submission.banned_by or submission.stickied:
			try:
				submission.mod.remove()
				comment.reply(f"You have successfully removed [this submission.]({submission.permalink})")
				comment.save()
				update_user_scores(comment)
				print(f"Saving !remove comment")
			except Exception as e:
				logger.error(f"Failed to remove submission {submission} with error {e}")
				comment.reply(f"Due to an error, I couldn't remove this submission: [{e}]")
			# Check for existing stickied comment by 'bot_account'
			already_stickied = False
			submission.comments.replace_more(limit=None)
			for top_level_comment in submission.comments:
				if top_level_comment.stickied and top_level_comment.author == os.getenv('BOT_USERNAME'):
					already_stickied = True
					break

			# Only add the removal reply if there isn't already a stickied comment by 'bot_account'
			if not already_stickied:
				try:
					removal_comment = submission.reply(get_removal_reply(comment.subreddit))
					removal_comment.mod.lock()
					removal_comment.mod.distinguish(how='yes', sticky=True)
				except Exception as e:
					logger.error(f"Failed to post removal comment on {submission} after removing it with error {e}")
			try:
				comment.save()
			except Exception as e:
				logger.error(f"Failed to save {comment} with error {e}")
			logger.info(f"Saving !remove comment")


def handle_restore_command(comment):
	"""Handles actions after finding !restore in a comment"""

	# Restore removed/locked comments by the bot in the last 24 hours
	if not re.match(r"! ?[Rr]estore", comment.body): 
		return
	author_name = comment.author.name
	flair = next(reddit.subreddit(f"{comment.subreddit}").flair(redditor=author_name))

	logger.info(f"Received comment restore request in r/{comment.subreddit} from u/{author_name}")
	# Must have 300 karma to restore comments.
	if not flair['flair_css_class'] in RESTORE_FLAIR_CLASSES:
		try:
			comment.reply(f"u/{comment.author}, I'm sorry you don't have the proper permissions. Level up by commenting more.")
			comment.save()
		except Exception as e:
			logger.error(f"Failed to reply to comment {comment} with error {e}")
		return None

	if ' ' in comment.body:  # if a username is provided
		target_username = comment.body.split(' ')[1].strip()  # get the username after !restore
		if target_username.startswith("u/"):  # if username has u/ prefix
			target_username = target_username[2:]  # remove the u/ prefix
	else:  # no username provided, use the author's name
		target_username = comment.author.name
	logger.info(f"Target for the comment restore is: u/{target_username}")
	comment.reply(f"Now attempting to restore posts/comments for u/{target_username}")
	comment_count, unlock_count = restore_comments(comment.subreddit, author_name)
	slumber.sleep(7)
	try:
		update_user_scores(comment)
		comment.reply(f"You restored {comment_count} comments, and unlocked {unlock_count} comments.")
		comment.save()
	except Exception as e:
		logger.error(f"Failed to reply to comment {comment} with error {e}")


def handle_sticky_command(comment):
	"""Handles actions after finding !sticky in a comment."""
	if not re.match(r"! ?[Ss]ticky", comment.body):
		return

	logger.info(f"Received submission sticky request in r/{comment.subreddit} from u/{comment.author.name}")
	try:
		submission = reddit.submission(id=comment.link_id.split('_')[1])

		# Check if there is a top sticky post
		if submission.stickied:
			# Unsticky the current top post
			submission.mod.sticky(state=False)

		# Stick the post to the bottom
		submission.mod.sticky(bottom=True)
	except Exception as e:
		logger.error(f"Failed to sticky parent submission of comment {comment} with error {e}")
		return

	logger.info(f"Post stickied {submission.id} in r/{submission.subreddit} due to a '!Sticky' command.")
	sticky_reply = f"Post [stickied](http://reddit.com{comment.permalink}) by mod u/{comment.author.name}"
	sticky_comment = submission.reply(sticky_reply)
	sticky_comment.mod.distinguish(how='yes', sticky=True)
	update_user_scores(comment)

	try:
		comment.save()
	except Exception as e:
		logger.error(f"Failed to save comment {comment} with error {e}")

	logger.info(f"Saving sticky request comment in r/{comment.subreddit}")


def handle_piss_command(comment):
	"""Handles actions after finding piss in a comment.
	Randomly comment that a conservative politician is a piss baby, choose from a list.
	"""
	if not re.match(r"\b[Pp]iss\b", comment.body):
		return
	logger.info(f"u/{comment.author} is taking a piss.")
	# select a random comeback
	comeback = random.choice(PISS_BABIES)
	# reply with the comeback
	logger.info("Saving piss comment.")
	try:
		comment.reply(f"{comeback} is a little piss baby.")
		comment.save()
		update_user_scores(comment)
	except Exception as e:
		logger.error(f"Failed to make reply to comment {comment} while trying to be a piss baby {e}")
		return


def restore_comments(subreddit, author_name):
	"""Restores comments on a subreddit."""
	# Restore removed and locked comments from the mod log.
	one_day_ago = datetime.utcnow() - timedelta(days=2)
	comment_count = 0
	unlock_count = 0
	try:
		mod_log = subreddit.mod.log(mod=os.getenv('BOT_USERNAME'), limit=None)
	except Exception as e:
		logger.error(f'Failed to retrieve mod log for {subreddit} with error {e}')
		return comment_count, unlock_count

	for log in mod_log:
		#logger.info(f"Found a log entry: {log.mod}")
		if datetime.utcfromtimestamp(
				log.created_utc) > one_day_ago and log.target_author.lower() == author_name.lower() and log.action in [
				'removecomment', 'lock']:
			try:
				comment = reddit.comment(id=log.target_fullname.split('_')[1])
				comment.mod.approve()
				comment_count += 1
				if comment.locked:
					comment.mod.unlock()
					unlock_count += 1
				logger.info(f"Restored and unlocked comment {comment.id} for user {author_name}.")    
			except Exception as e:
				logger.error(f"Failed to find, approve, or unlock comment from modlog entry {log} with error {e}")
				return
			logger.info(f"Restored and unlocked comment {comment.id} for user {author_name}.")
	return comment_count, unlock_count



def handle_leaderboard_command(comment):
	"""Checks comment for a leaderboard ping."""
	if not re.match(r"!? ?[Ll]eaderboard", comment.body):
		return

	# Generate the leaderboard string
	user_scores = load_user_scores(comment.subreddit)
	leaderboard_string = format_leaderboard(user_scores, True)
	logger.info("Successfully fetched the leaderboard, preparing to post.")
	# Submit the leaderboard as a Reddit comment reply
	try:
		comment.reply(leaderboard_string)
		comment.save()
	except Exception as e:
		logger.error(f'Failed to reply to leaderboard comment  with error {e}')


def format_leaderboard(user_scores, flag):
	if flag:
		sorted_scores = sorted(user_scores.items(), key=lambda x: sum(x[1].values()), reverse=True)[:5]
	else:
		sorted_scores = sorted(user_scores.items(), key=lambda x: sum(x[1].values()), reverse=True)
	leaderboard = []
	for user, scores in sorted_scores:
		actions = [f"{action}: {count}" for action, count in scores.items() if count >= 1]
		leaderboard.append(f"**{user}**: {' | '.join(actions)}")
	return "\n\n".join(leaderboard)


def save_user_scores(subreddit, user_scores):
	content = json.dumps(user_scores)
	try:
		reddit.subreddit(subreddit.display_name).wiki[f"{USER_SCOREBOARD_WIKI_PAGE}"].edit(content=content)
	except Exception as e:
		logger.error(F"Error: Something went wrong saving user scores: [{e}]")


def load_user_scores(subreddit):
	try:
		content = reddit.subreddit(subreddit.display_name).wiki[f"{USER_SCOREBOARD_WIKI_PAGE}"].content_md
		if content:
			return json.loads(content)
		else:
			return {}
	except Exception as e:
		print(f'Error loading user scores: {e}')
		return {}


def update_user_scores(comment):
	"""Update the user scoreboard"""
	logger.info("Loading user scores")
	user_scores = load_user_scores(comment.subreddit)

	if comment.author:
		author_name = comment.author.name
		if author_name not in user_scores:
			user_scores[author_name] = {
				"Lock": 0,
				"Restore": 0,
				"Remove": 0,
				"Unlock": 0,
				"Sticky": 0,
				"Decode CRT": 0,
				"Users banned": 0,
				"Piss babies birthed": 0
			}

		# Increment the count for each action
		if re.match(r"! ?[Ll]ock", comment.body):
			user_scores[author_name]["Lock"] = user_scores[author_name].get("Lock", 0) + 1
		elif re.match(r"! ?[Rr]estore", comment.body):
			user_scores[author_name]["Restore"] = user_scores[author_name].get("Restore", 0) + 1
		elif re.match(r"! ?[Rr]emove", comment.body):
			user_scores[author_name]["Remove"] = user_scores[author_name].get("Remove", 0) + 1
		elif re.match(r"! ?[Uu]nlock", comment.body):
			user_scores[author_name]["Unlock"] = user_scores[author_name].get("Unlock", 0) + 1
		elif re.match(r"! ?[Ss]ticky", comment.body):
			user_scores[author_name]["Sticky"] = user_scores[author_name].get("Sticky", 0) + 1
		elif re.match(r"!? ?[Cc][Rr][Tt]", comment.body):
			user_scores[author_name]["Decode CRT"] = user_scores[author_name].get("Decode CRT", 0) + 1
		elif re.match(r"! ?[Bb]an", comment.body):
			user_scores[author_name]["Users banned"] = user_scores[author_name].get("Users banned", 0) + 1
		elif re.match(r"!? ?[Pp]iss", comment.body):
			user_scores[author_name]["Piss babies birthed"] = user_scores[author_name].get("Piss babies birthed", 0) + 1

	save_user_scores(comment.subreddit, user_scores)


def handle_crt_command(comment):
	"""Checks comment for a CRT reference."""
	if not re.match(r".*\b[Cc][Rr][Tt]\b.*", comment.body):
		return

	if comment.author.name != os.getenv('BOT_USERNAME'): #reddit.user.me():
		comment.refresh()
		logger.info(f"RED ALERT: Some user, u/{comment.author} is talking about CRT on the Subreddit.") 
		mommy_what_is_crt = decode_crt()
		logger.info(f"u/{comment.author} decoded CRT for us.")
		
		update_user_scores(comment)
		logger.info("Updated leaderboard.")

		try:
			comment.reply(mommy_what_is_crt)
			logger.info("Replied to CRT comment.")
			comment.save()
		except Exception as e:
			logger.error(f'Failed to reply to CRT comment with error {e}')

def handle_modlog_command(comment):
	if not re.match(r"!? ?[Mm]od.?[Ll]og", comment.body):
		return

	user_scores = load_user_scores(comment.subreddit)
	leaderboard_string = format_leaderboard(user_scores, False)
	try:
		comment.reply(leaderboard_string)
		comment.save()
	except Exception as e:
		logger.error(f'Failed to reply to mod log command with error {e}')

def handle_harassment_command(comment):
	if not re.match(r".*[A-Za-z0-9]$", comment.id) and random.random() < 0.5:
		return

	user_scores = load_user_scores(comment.subreddit)
	reply, new_reply = mod_harassment(comment, user_scores)
	#logger.info(f"Mod Harassment message sent: {reply}")
	try:
		comment.save()
	except Exception as e:
		logger.error(f'Failed to save harassment target comment with error {e}')

def mod_harassment(comment, user_scores):
	"""Randomly check 50 out of the last 1000 comments for a mod "simulation" candidate.  User must have logged an action already and thus opened themselves up for harassment."""
	reply_list = MOD_HARASSMENT_REPLY_LIST
	
	if comment.author != os.getenv('BOT_USERNAME')  and comment.author in user_scores:
		logger.info(f"Found mod harassment comment candidate: u/{comment.author}")
		# Choose a random reply from the list
		reply = random.choice(reply_list)
		new_reply = reply + MOD_HARASSMENT_FOOTER
		# Reply to the comment with the chosen reply
		try:
			comment.reply(new_reply)
			logger.info(f"Mod Harassment message sent: {reply}")
		except Exception as e:
			logger.error(f"Error: failed to reply to mod harassment comment candidate: [{e}]")	
		
		return reply, new_reply
	return None, None


def handle_ban_command(comment):
	if not re.match(r"! ?[Bb]an", comment.body):
		return
	ph_mod_names_list = []
	for moderator in comment.subreddit.moderator():
		ph_mod_names_list.append(f"{moderator.name}")
	author_name = comment.author.name
	# Get the list of users on the cooldown list.
	lock_list = get_lock_list(comment.subreddit)
	if author_name in lock_list:
		# Check is user needs a cooldown
		time_since_last_command = datetime.now() - lock_list[author_name]
		if time_since_last_command < LOCK_COMMAND_COOLDOWN:
			logger.info(
				f"u/{author_name} is spamming !ban command in {comment.subreddit}, ignoring this command.")
			return
	flair = next(reddit.subreddit(f"{comment.subreddit}").flair(redditor=author_name))
	# Must have full perms to ban, 2000 comment karma.
	if not flair['flair_css_class'] in FULL_PERMS_FLAIR_CLASSES:
		try:
			comment.reply(f"u/{comment.author}, I'm sorry you don't have the proper permissions. Level up by commenting more.")
			comment.save()
		except Exception as e:
			logger.error(f"Failed to reply to ban request comment {comment} with error {e}")
		return None

	logger.info(f"Received ban request in r/{comment.subreddit} from u/{author_name}")
	
	if ' ' in comment.body:  # if a username is provided
		target_username = comment.body.split(' ')[1].strip()  # get the username after !restore
		if target_username.startswith("u/"):  # if username has u/ prefix
			target_username = target_username[2:]  # remove the u/ prefix
	else:  # no username provided, use the author's name
		target_username = comment.author.name
	logger.info(f"Target for the ban is: u/{target_username}")
	
	# Validate the target user
	try:
		target_user = reddit.redditor(target_username)
	except (prawcore.exceptions.NotFound, prawcore.exceptions.Forbidden):
		try:
			comment.reply(f"User u/{target_username} does not exist. Please make sure you spelled the username correctly and try again.")
			comment.save()
		except Exception as e:
			logger.error(f"Failed to reply to comment about non-existent user: [{e}]")
		return None

	if target_username in ph_mod_names_list or target_user.is_employee:
		try:
			comment.reply("I'm sorry, but you cannot ban a moderator or an admin from the subreddit. Nice try, though.")
			comment.save()
		except Exception as e:
			logger.error(f"Failed to reply to comment informing user they cannot ban a mod or adnim.")	
	elif target_username not in get_banlist(comment.subreddit):
		command_ban_message = get_ban_message("politicalhumor", "ban_command")
		new_command_ban_message = command_ban_message.replace("{author}", author_name)
		logger.info(f"BAN MESSAGE: {new_command_ban_message}")
		try:
			ban_user(comment.subreddit,
					 target_username,
					 COMMENT_BAN_DURATION_DAYS,
					 ban_reason = f"{comment.permalink}",
					 ban_message=f"{new_command_ban_message}")
		except Exception as e:
			logger.error(f"Error banning user: [{e}]")	
			try:
				comment.reply("I can't ban this user due to error: [{e}]")
				comment.save()
			except Exception as e:
				logger.error(f"I could not reply that I couldn't ban a user: [{e}]")

		logger.info(f'Banned user {target_username} in r/{comment.subreddit} for negative comment with score {comment.score}.')
		# Add to banlist after successful ban
		add_to_banlist(comment.subreddit, target_username)
		# Comment.save() is called to keep from removing every comment on the thread.
		update_user_scores(comment)
		# Add the user to the lock list wiki page for cooldown restriction.
		update_lock_list(comment.subreddit, author_name, datetime.now())
		logger.info(f"Cooldown list updated, added {author_name}.")
		try:	
			comment.reply(f"u/{target_username} was banned for one day.")
			comment.save()
		except Exception as e:
			logger.error(f"I could not reply to a comment: [{e}]")
		logger.info("Saving ban request comment.")
	
	else:
		try:
			comment.reply("This user is already banned.")
			comment.save()
		except Exception as e:
			logger.error(f"I could not reply to this comment: [{e}]")


def get_removal_reply(subreddit_display_name):
	"""Retrieves removal reply from subreddit config."""
	subreddit_config = config.get('subreddits', {}).get(subreddit_display_name, {})
	if not subreddit_config.removal_reply:
		logger.error(f"No removal reply found for {subreddit_display_name}")
		# TODO Better default removal reply
		return f"Your comment has been removed by {os.getenv('BOT_USERNAME')}."
	else:
		return subreddit_config.removal_reply


def get_lock_list(subreddit):
	"""Retrieves cooldown / lock list from the subreddits wiki."""
	lock_list = {}
	try:
		content = subreddit.wiki['banout/lock_list'].content_md
	except Exception as e:
		logger.error(f"Failed to retrieve lock_list from {subreddit}")
		return lock_list

	if content:
		for line in content.split('\n'):
			try:
				name, time = line.split(',')
				lock_list[name] = datetime.strptime(time.strip(), "%Y-%m-%d %H:%M:%S")
			except ValueError as ve:
				logger.error(f'Error parsing time from locklist for user subreddit {subreddit.display_name}: {ve}')
	return lock_list


def update_lock_list(subreddit, name, time):
	"""Adds a name and time to the cooldown / lock list of a subreddit."""
	# Update the cooldown list
	lock_list = get_lock_list(subreddit)
	lock_list[name] = time
	content = '\n'.join([f'{k},{v.strftime("%Y-%m-%d %H:%M:%S")}' for k, v in lock_list.items()])
	try:
		subreddit.wiki[f"{COOLDOWN_LIST_WIKI_PAGE}"].edit(content=content)
	except Exception as e:
		logger.error(f"Failed to update cooldown list for subreddit {subreddit} with name {name} and time {time} - received error {e}")

def check_inbox(subreddit):
	"""
	Process the reddit inbox for the ban appeal process.
	"""
	logger.info("Checking for new messages...")
	try:
		for msg in reddit.inbox.unread(limit=100):
			# Check if a valid message.
			if isinstance(msg, Message):
				msg_body = msg.body.lower()
				msg_subject = msg.subject.lower()

				if "i would like to appeal my ban" in msg_subject:
					captured_appeal_text = ""
					# This function is a message relay, banned_user will be the sender of the appeal message.
					banned_user = msg.author
					logger.info(f"Ban appeal request received from {banned_user}.")
					# Fetch the username
					match = re.search(r"u/([a-zA-Z0-9_-]{3,20})", msg_body)
					# Fetch any appeal text that they left in the message.
					appeal_text = re.search(r"here:(.*)", msg_body, flags=re.DOTALL)
					captured_appeal_text = appeal_text.group(1)
					if match:
						banning_mod = match.group(1)
						logger.info(f"Found the banning mod username in modmail: {banning_mod}")
					if appeal_text:	
						captured_appeal_text = captured_appeal_text.strip()
					try:
						reddit.redditor(f"{banning_mod}").message(subject=f"u/{banned_user} would like to appeal a ban.", message=f"u/{banned_user} said:\n\n> {captured_appeal_text}.\n\n---\n\nIf you would like to unban u/{banned_user}, reply to this message with ```!unban {banned_user}```.\n\nThank you for being a mod of r/PoliticalHumor.")
						msg.mark_read()
					except Exception as e:
						logger.error(f"\t### ERROR - An error occurred sending message...[{e}]")

				if "would like to appeal a ban" in msg_subject:
					#subreddit = reddit.subreddit("PoliticalHumor")
					if re.match(r"!?[Uu]nban", msg_body): 
						if ' ' in msg_body:  # if a username is provided
							target_username = msg_body.split(' ')[1].strip()  # get the username after !restore
							if target_username.startswith("u/"):  # if username has u/ prefix
								target_username = target_username[2:]  # remove the u/ prefix
						else:  # no username provided, use the author's name
							target_username = msg.author
						logger.info(f"Target for the unban is: u/{target_username}")
				
						try:
							subreddit.banned.remove(target_username)
							logger.info(f"u/{target_username} was unbanned.")
						except prawcore.exceptions.NotFound as e:
							# ShadowBanned
							logger.error(f"An error occurred.[{e}]")	
						except prawcore.exceptions.Forbidden as e:
							# Suspended User
							logger.error(f"An error occurred.[{e}]")
						except prawcore.exceptions.ServerError as e:
							logger.error(f"### ERROR - A Reddit server error occurred. Sleeping 3 min before trying again...[{e}]")
							time.sleep(180)
							pass
						except Exception as e:
							logger.error(f"### ERROR - Another type of error occurred...[{e}]")
						try:
							msg.reply(f"You have unbanned {target_username}.")
						except Exception as e:
							logger.error(f"### ERROR - An error occurred sending message...[{e}]")	
						slumber.sleep(5)
						try:
							reddit.redditor(f"{banned_user}").message(subject="You've been unbanned.", message="You have been unbanned.  Thank you for using r/PoliticalHumor.")
							msg.mark_read()	
						except Exception as e:
							logger.error(f"### ERROR - An error occurred sending message...[{e}]")		
						
	except prawcore.exceptions.ServerError as e:
			logger.error(
				f"### ERROR -A Reddit server error occurred. Sleeping 3 min before trying again...[{e}]"
			)
			time.sleep(180)
			pass
	except Exception as e:
		logger.error(f"### ERROR - COULDN'T PROCESS INBOX.[{e}]")


def main():
	# Define your subreddit names, one name only is fine.
	subreddit_names = [config['subreddits'][subreddit]['name'] for subreddit in config.get('subreddits', {})]

	if not subreddit_names or len(subreddit_names) == 0:
		logger.error("Subreddit list empty - cannot run - check config.json")
	while True:
		for subreddit_name in subreddit_names:
			logger.info(f'Democracy Bot now applying non-consensual democracy to {subreddit_name}')
			subreddit = reddit.subreddit(subreddit_name)
			check_inbox(subreddit)
			check_submissions(subreddit)
			check_comments(subreddit)
			unlock_comments_and_approve(subreddit_name)
			banlist = get_banlist(subreddit)
			for name, time in banlist.items():
				if datetime.now() > time + timedelta(days=1):
					remove_from_banlist(subreddit, name)
			check_inbox(subreddit)
			# Loop every X seconds, defined at top
			sleep_until = (datetime.now() + timedelta(seconds=SLEEP_SECONDS)).strftime('%H:%M %p')  # 230 seconds
			logger.info(f'Sleeping until {sleep_until}\n\n')  # %Y-%m-%d
			slumber.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
	main()
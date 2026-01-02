# MautrFxEmbed

A maubot plugin that passively scans your chats for links to X/Twitter, BlueSky, Mastodon posts, Instagram reels and responds with a message that embeds the content of said links. This project was inspired by better link embeds provided by FxEmbed on Discord.  

### This plugin is a work in progress. The layout of the messages and available features are subject to change. You may run into unexpected bugs. Use at your own risk.

## Usage

Just paste a link in the chat. The bot will scan the message and if it matches the criteria, it will provide an embed.  

## Configuration

You can configure the plugin in maubot's control panel.  
* `nitter_redirect` - this setting controls whether plugin will replace most of X/Twitter links within an embed with links using address defined in `nitter_url` (default: `true`)  
* `nitter_url`: address of a Nitter instance (default: `nitter.net`)  
* `bsky_player` - address of a HLS media player that is capable of playing BlueSky video links. (default: `https://korba.neocities.org/player?url=`)  

## Notes

**Q:** Why BlueSky videos open on a website with some suspicious looking URL?  
**A:** BlueSky doesn't provide nice links that can be played in a browser out of the box. For that, you need a HLS player. I couldn't find existing trustworthy website with such a player for this so I made my own and put it on my page on neocities.org. If you want, you can host your own player. The player code is included in player.html inside this repository.

**Q:** But why don't you just attach the video to the message instead of doing this mumbo jumbo with custom media player that opens inside a browser?  
**A:** File size limit can differ depending on a Matrix server. It's usually around 100 MiB. It also costs money to host a Matrix server. Storing big blobs of data increases these costs. I don't control file size limits on social media. Twitter videos can be up to 16 GiB in size. I am not uploading that anywhere and becoming a burden to some poor Synapse administrator because someone spammed a chat with Twitter links. You can play your videos in a browser.  

**Q:** Will you add other services?  
**A:** I might. Not sure yet.  

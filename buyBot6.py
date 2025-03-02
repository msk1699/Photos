l#This is th first buy bot created in May 2024 by msk_technology. This is the version 3.0

import json
from web3 import Web3
from decimal import Decimal,ROUND_DOWN
import re
import time
from web3.middleware import construct_simple_cache_middleware, geth_poa_middleware
import asyncio
from telegram import Bot,Update
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, filters, CallbackContext
)
from pycoingecko import CoinGeckoAPI
from multiprocessing import Manager, Process
import os
import config


#important Urls
OMX_url="https://mainapi.omaxray.com"
omaxScanUrl="https://omaxscan.com/"
chartUrl="https://www.geckoterminal.com/omax-chain/pools/"

#create web3 instance
web3=Web3(Web3.HTTPProvider(OMX_url))


# Replace 'YOUR_BOT_TOKEN' with your actual bot token
bot_token = config.TEST_BOT_ID

bot = Bot(token=bot_token)
myUserName = 'msk_technology'
RECEIVING_TOKEN_DETAILS = 0
RECEIVING_CHAT_ID = 1
DELETE_TOKEN=2
RECEIVING_STEP_SIZE = 3
RECEIVING_MIN_LIMIT=4
CHECK_TOKEN_AND_RESPOND=5
RECEIVING_SUPPLY=6
RECEIVING_EMOJI=7




#this piece of code was added to handle proof of authority chain
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

cg = CoinGeckoAPI() #for coingecko data

#function to load ABI block_data

def get_abi(abi_txt):
    with open(abi_txt,'r') as _abiFile:
        _abi=_abiFile.read()
        _abi=json.loads(_abi)
        return _abi


#contract addresses
OmaxRouterAddress=Web3.to_checksum_address("0xfC12B1dc096b7728122D0A03403Fa3239F103537")
FactoryAddress=Web3.to_checksum_address("0x441b9333D1D1ccAd27f2755e69d24E60c9d8F9CF")
DataFetcherAddress=Web3.to_checksum_address("0x42Cf3EEfDbaD13E653f0EA329dAE5015B9f6a8DC")
OmaxFunAddress=Web3.to_checksum_address("0x1f53E9893Fa64a9a44EA4EF4b26CFfD1212D40E1")

WOMAX=Web3.to_checksum_address("0x373e4b4E4D328927bc398A9B50e0082C6f91B7bb")
USDT=Web3.to_checksum_address("0x277e926A0E81b9e258dAb620dc62dc84d15A936D")
Tara=Web3.to_checksum_address("0x902FA6386a5eda84A3d3C87a209283a77D3Bde5A")
Pheonix=Web3.to_checksum_address("0x3B28e982662367cc348efd22b345d8a7e42bA46b")
DeadAddress=Web3.to_checksum_address("0x000000000000000000000000000000000000dEaD")

#Intiate Omax Router Contract
Omax_router=web3.eth.contract(address=OmaxRouterAddress,abi=get_abi('router_abi.txt'))
Factory=web3.eth.contract(address=FactoryAddress,abi=get_abi('factory_abi.txt'))
DataFetcher=web3.eth.contract(address=DataFetcherAddress,abi=get_abi('dataFetcher_abi.txt'))
OmaxFun=web3.eth.contract(address=OmaxFunAddress,abi=get_abi('omaxfun_abi.txt'))


#define common function names
pattern = r"<Function\s+(\w+)\("
function1="swapExactETHForTokens"
function2="swapETHForExactTokens"
function3="buy"

defaultStepSize=5000
defaultMinAmountLimit=10
defaultEmoji='🔥'


#this is the event signature that is used to find transfer events in logs
event_signature = "Transfer(address,address,uint256)"
# Compute the Keccak-256 hash of the event signature
event_hash = web3.keccak(text=event_signature).hex()


#classe to store token objects and details
class Token:
    def __init__(self, _symbol, _chatId,_decimals,_poolAddress,_stepSize,_emoji,_minAmountLimit,_circulationSupply):
        self.symbol = _symbol
        self.chatId = _chatId
        self.decimals = _decimals
        self.poolAddress=_poolAddress
        self.stepSize=_stepSize
        self.emoji=_emoji
        self.minAmountLimit=_minAmountLimit
        self.circulationSupply=_circulationSupply




Tokens={}




#Some Basic Functions
def getSymbol(tokenContract):
    symbol=DataFetcher.functions.getSymbol(tokenContract).call()
    return symbol

def getDecimals(tokenContract):
    decimals=DataFetcher.functions.getDecimals(tokenContract).call()
    return decimals

def getPoolAddress(tokenContract):
    poolAddress=Factory.functions.getPair(WOMAX,tokenContract).call()
    poolAddress=Web3.to_checksum_address(poolAddress)
    return poolAddress

def getBalance(tokenContract,walletAddress):
    balance=DataFetcher.functions.getTokenBalance(tokenContract,walletAddress).call()
    balance=balance/10**getDecimals(tokenContract)
    return balance


def getCirculationSupply(tokenContract):
    totalSupply=DataFetcher.functions.getTotalSupply(tokenContract).call()
    totalSupply=totalSupply/10**getDecimals(tokenContract)
    supplyBurned=getBalance(tokenContract,DeadAddress)
    circulationSupply=totalSupply-supplyBurned
    return circulationSupply


def isTokenStored(tokenContract):
    storedTokens = readJSONfile("Tokens.json")
    if not storedTokens:  # Check if storedTokens is empty or None
        return False
    for token in storedTokens:
        if token['contractAddress'] == tokenContract:
            return True

    return False


def storeTokens(_contractAddress,_chatID):
    if not isTokenStored(_contractAddress):
        newTokenInfo={}
        newTokenInfo['contractAddress']=_contractAddress
        newTokenInfo['chatID']=_chatID
        tokensData = readJSONfile("Tokens.json")
        # Check if tokensData is a list, if not, initialize it as a list
        if not isinstance(tokensData, list):
            tokensData = []
        tokensData.append(newTokenInfo)
        with open('Tokens.json', 'w') as file:
            json.dump(tokensData, file, indent=4)

def addStoredTokens():
    storedTokens = readJSONfile("Tokens.json")
    for token in storedTokens:
        addToken(token["contractAddress"],token["chatID"])


def readJSONfile(filePath):
    try:
        with open(filePath, 'r') as file:
            TokenData = json.load(file)
            return TokenData
    except FileNotFoundError:
        TokenData = {}
    except json.JSONDecodeError:
        TokenData = {}


def updateChange(command,tokenContract,value):
    newTokenInfo={}
    newTokenInfo['command']=command
    newTokenInfo['contractAddress']=tokenContract
    newTokenInfo['value']=value
    with open('Updates.json', 'w') as file:
        json.dump(newTokenInfo, file, indent=4)


def manageUpdate():
    updatedData=readJSONfile("Updates.json")
    command = updatedData["command"]
    contractAddress=updatedData["contractAddress"]
    value=updatedData["value"]
    if command =="addToken":
        addToken(contractAddress,value)

    elif command =="deleteToken":
        deleteToken(contractAddress)

    elif command =="updateStepSize":
        Tokens[contractAddress].stepSize=int(value)
        print(f"Step Size Updated for: {contractAddress}")
        print(f"New Step Size: {value}")

    elif command=="updateMinLimit":
        Tokens[contractAddress].minAmountLimit=int(value)
        print(f"Minimum Amount Limit Updated for: {contractAddress}")
        print(f"New Minimum Amount Limit: {value}")

    elif command=="updateSupply":
        Tokens[contractAddress].circulationSupply=int(value)
        print(f"Circulation Supply Updated for: {contractAddress}")
        print(f"New Circulation Supply: {value}")

    elif command=="updateEmoji":
        Tokens[contractAddress].emoji=value
        print(f"Emoji Updated for: {contractAddress}")
        print(f"New Emoji: {value}")


    os.remove("Updates.json")


def deleteToken(tokenContract):
    del Tokens[tokenContract]
    storedTokens=readJSONfile("Tokens.json")
    newTokenInfo=[]
    for token in storedTokens:
        if token['contractAddress']==tokenContract:
            pass
        else:
            newTokenInfo.append(token)

    with open('Tokens.json', 'w') as file:
        json.dump(newTokenInfo, file, indent=4)
    print(f"Token:{tokenContract} Deleted Successfully")







##########################################################################

#Main Functions for Blockchain Scan

#This function adds a new token to the Tokens List
def addToken(contractAddress,chatId):
    contractAddress=Web3.to_checksum_address(contractAddress)
    symbol=getSymbol(contractAddress)
    decimals=getDecimals(contractAddress)
    poolAddress=getPoolAddress(contractAddress)
    circulationSupply=getCirculationSupply(contractAddress)


    #create token object and append that object in Tokens dictionary with reference to contractAddress
    Tokens[contractAddress]=Token(symbol,chatId,decimals,poolAddress,
                                defaultStepSize,defaultEmoji,defaultMinAmountLimit,
                                circulationSupply)

    storeTokens(contractAddress,chatId)
    print(f"Token:{contractAddress} Added Successfully")


#This function gets Current Omax Price from CoinGecko
async def getOmaxPrice():
    token_id = 'omax-token'
    currency = 'usd'
    try:
        # Get the current price of the token
        price = cg.get_price(ids=token_id, vs_currencies=currency)
        return Decimal(price[token_id][currency])
    except Exception as e:
        print(f"Error fetching price: {e}")
        return None


#This function calculates Price of a Token Based on Omax Price
async def calculatePrice(_contractAddress,amountSpent,amountReceived):
    omaxPrice = await getOmaxPrice()  # Fetch the OMAX price asynchronously
    omaxPrice = Decimal(omaxPrice)
    amountSpent = Decimal(amountSpent)
    amountReceived = Decimal(amountReceived)

    if amountReceived == 0:  # Prevent division by zero
        return 0

    tokenAmountReceived=Decimal(amountReceived/10**Tokens[_contractAddress].decimals)

    tokenPrice = (amountSpent * omaxPrice) /tokenAmountReceived
    tokenPrice=format(tokenPrice, '.12f')

    return tokenPrice


def fileExist(fileName):
    return os.path.exists(fileName)


#This function sends semmage to the telegram bot
async def sendMessage(bot, contractAddress,buyer,amountSpent,amountReceived,txHash,tokenPrice):
    chatId=Tokens[contractAddress].chatId
    tokenSymbol=Tokens[contractAddress].symbol
    tokenAmountReceived=amountReceived/10**Tokens[contractAddress].decimals
    tokenAmountReceived= round(tokenAmountReceived, 2)
    amountSpentUsd=Decimal(await getOmaxPrice()*amountSpent)
    amountSpentUsd=format(amountSpentUsd, '.5f')
    marketCap = float(tokenPrice) * float(Tokens[contractAddress].circulationSupply)

    noOfEmojis=int(amountSpent/Tokens[contractAddress].stepSize)

    fixed_message = f"<b>{tokenSymbol} Token Buy</b>\n"
    fixed_message += Tokens[contractAddress].emoji * max(1, noOfEmojis) + "\n"

    tx_url = f"{omaxScanUrl}/tx/{txHash}"
    chart_url = f"{chartUrl}/{Tokens[contractAddress].poolAddress}"
    buyer_url = f"{omaxScanUrl}/address/{buyer}"
    omaxSwap_url="https://swap.omax.app/swap"

    data_message=(
        f"<b>Spent:</b> {format(amountSpent,',.2f')} <b>WOMAX</b>\n"
        f"($ {amountSpentUsd})\n"
        f"<b>Got:</b> {format(float(tokenAmountReceived),',')} <b>{tokenSymbol}</b>\n"
        f"<b>Price:</b> $ {tokenPrice} \n"
        f"<b>MCap:</b> $ {format(marketCap,',.2f')} \n"

        f"<a href='{tx_url}'>TX</a> | "
        f"<a href='{chart_url}'>Chart</a> | "
        f"<a href='{buyer_url}'>Buyer</a> | "
        f"<a href='{omaxSwap_url}'>OmaxSwap</a> ")

    full_message=fixed_message+data_message
    imageName=tokenSymbol+".jpg"
    videoName=tokenSymbol+".mp4"

    if fileExist(imageName) and amountSpent >=10000 and amountSpent <100000:
        await sendImage(bot,contractAddress,chatId,imageName,full_message)

    elif fileExist(videoName) and amountSpent >=100000:
        await sendVideo(bot,contractAddress,chatId,videoName,full_message)

#### MAde Specially for $FUN Token
    elif tokenSymbol.strip() == '$FUN' and amountSpent >= 10000 and amountSpent < 100000:
        await sendImage(bot,contractAddress,chatId,'FUN.jpg',full_message)

    elif tokenSymbol.strip() == '$FUN' and amountSpent >= 100000:
        await sendVideo(bot,contractAddress,chatId,'FUN.mp4',full_message)

#######
    else:
        try:
            await bot.send_message(chat_id=chatId, text=full_message, parse_mode='HTML',disable_web_page_preview=True)
            print("Message sent successfully!")
        except TelegramError as e:
            print(f"Failed to send message: {e}")


async def sendImage(bot,contractAddress,chatId,imageName,caption):
    try:
        with open(imageName, 'rb') as photo_file:
            await bot.send_photo(chat_id=chatId, photo=photo_file, caption=caption,parse_mode='HTML')
        print("Image sent successfully!")
    except TelegramError as e:
        print(f"Failed to send image: {e}")


async def sendVideo(bot,contractAddress,chatId,videoName,caption):
    try:
        with open(videoName,'rb') as video_file:
            await bot.send_video(chat_id=chatId,video=video_file,caption=caption,parse_mode='HTML')

        print("Video Sent Successfully")

    except TelegramError as e:
        print(f"Failed to send video: {e}")


async def checkLogAndSendMessage(log,contractAddress,buyer,omaxAmountIn,tx_hash_hex):
    if len(log['topics']) == 3 :
        topics=log['topics']
        # Event signature
        functionSign=topics[0]
        function_hex_string = functionSign.hex()

        if function_hex_string == event_hash:
            #print("hashes mached")
            to_address=topics[2]
            to_address=to_address.hex()
            normalized_address = '0x' + to_address.lower().lstrip('0x').zfill(40)
            checksum_address = Web3.to_checksum_address(normalized_address)

            if checksum_address == buyer:
                binary_data=log['data']
                amountGot = int.from_bytes(binary_data, byteorder='big')
                tokenPrice=await calculatePrice(contractAddress,omaxAmountIn,amountGot)
                await sendMessage(bot, contractAddress,buyer,omaxAmountIn,amountGot,tx_hash_hex,tokenPrice)


async def blockScan():
    while True:
        #get latest block data from blockchain
        try:
            block_data=web3.eth.get_block(block_identifier='latest',full_transactions=True)
            block_number=block_data['number']
            #print("Block Number: "+ str(block_number))
            txns=block_data['transactions'] #extract all the txns data from block data
            if fileExist("Updates.json"):
                print("Update File Found")
                manageUpdate()
            for tx in txns:
                data=tx['input']
                if tx['to']==OmaxRouterAddress:
                    decodedData=Omax_router.decode_function_input(data)
                    function_signature=str(decodedData[0])
                    matches = re.findall(pattern, function_signature)
                    function_name=matches[0]

                    #if any tx is for swapping from omax
                    if function_name==function1 or function_name==function2:
                        print("Swapping from Omax")
                        functionData=decodedData[1]
                        path=functionData['path']
                        tokenAddress=path[1]
                        if tokenAddress in Tokens:
                            print("Token Buy")
                            buyer=functionData['to']
                            value_wei = tx['value'] # Access the 'value' field (in wei)
                            omaxAmountIn = web3.from_wei(value_wei, 'ether') #convert from wei
                            #omaxAmountIn=round(omaxAmountIn, 2)

                            if omaxAmountIn >= Tokens[tokenAddress].minAmountLimit:
                                tx_hash=tx['hash']
                                tx_hash_hex=web3.to_hex(tx_hash)
                                tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                                for log in tx_receipt.logs:
                                    await checkLogAndSendMessage(log,tokenAddress,buyer,omaxAmountIn,tx_hash_hex)

                elif tx['to']==OmaxFunAddress:
                    decodedData=OmaxFun.decode_function_input(data)
                    functionData=decodedData[1]
                    tokenAddress=functionData['token']
                    function_signature=str(decodedData[0])
                    matches = re.findall(pattern, function_signature)
                    function_name=matches[0]
                    if function_name==function3:
                        print("buy from OmaxFun")
                        print(tokenAddress)

                        if tokenAddress in Tokens:
                            buyer=tx['from']
                            value_wei = tx['value'] # Access the 'value' field (in wei)
                            omaxAmountIn = web3.from_wei(value_wei, 'ether') #convert from wei

                            if omaxAmountIn >= Tokens[tokenAddress].minAmountLimit:
                                tx_hash=tx['hash']
                                tx_hash_hex=web3.to_hex(tx_hash)
                                tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                                for log in tx_receipt.logs:
                                    await checkLogAndSendMessage(log,tokenAddress,buyer,omaxAmountIn,tx_hash_hex)





        except Exception as e:
                print(f'error occured:{e}')


        while web3.eth.block_number==block_number: #wait for new block
            await asyncio.sleep(0.5)



################################################################################



#These Function are related to telegram bot , to handle commands and other stuff

async def startConvo(update: Update, context: CallbackContext) -> None:
    username = update.message.from_user.username
    if username:
        if username == myUserName:
            welcome_message = f'Hello msk! How can I help..'
        else:
            welcome_message = f'Hello {username}! I am the First Buy Bot on Omax Blockchain.'
    else:
        welcome_message = 'Hello! I am the First Buy Bot on Omax Blockchain.'
    await update.message.reply_text(welcome_message)



async def addTokenCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'add_token'
        await update.message.reply_text('Please send the Token Contract Address.')
        return RECEIVING_TOKEN_DETAILS
    else:
        await update.message.reply_text('You are not authorized to add tokens. Please contact @msk_technology for help.')
        return ConversationHandler.END



async def deleteTokensCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'delete_token'
        await update.message.reply_text('Please send the Token Contract Address you want to delete.')
        return DELETE_TOKEN
    else:
        await update.message.reply_text('You are not authorized to delete tokens. Please contact @msk_technology for help.')
        return ConversationHandler.END


async def updateSupplyCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'update_supply'
        await update.message.reply_text('Please send the Token Contract Address you want to make changes.')
        return RECEIVING_TOKEN_DETAILS
    else:
        await update.message.reply_text('You are not authorized to Update Token Supply. Please contact @msk_technology for help.')
        return ConversationHandler.END


async def updateEmojiCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'update_emoji'
        await update.message.reply_text('Please send the Token Contract Address you want to make changes.')
        return RECEIVING_TOKEN_DETAILS
    else:
        await update.message.reply_text('You are not authorized to Update Emoji. Please contact @msk_technology for help.')
        return ConversationHandler.END


async def updateMinLimitCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'update_min_limit'
        await update.message.reply_text('Please send the Token Contract Address.')
        return RECEIVING_TOKEN_DETAILS
    else:
        await update.message.reply_text('You are not authorized to Update Minimum Limit. Please contact @msk_technology for help.')
        return ConversationHandler.END



async def updateStepSizeCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'update_step_size'
        await update.message.reply_text('Please send the Token Contract Address.')
        return RECEIVING_TOKEN_DETAILS
    else:
        await update.message.reply_text('You are not authorized to Update Step Sizes. Please contact @msk_technology for help.')
        return ConversationHandler.END




async def checkTokenCommand(update: Update, context: CallbackContext) -> int:
    username = update.message.from_user.username
    if username and username == myUserName:
        context.user_data['action'] = 'check_token'
        await update.message.reply_text('Please send the Token Contract Address you wish to check.')
        return CHECK_TOKEN_AND_RESPOND
    else:
        await update.message.reply_text('You are not authorized for this task. Please contact @msk_technology for help.')
        return ConversationHandler.END


async def receiveTokenContract(update: Update, context: CallbackContext) -> int:
    token_contract = update.message.text
    action = context.user_data.get('action')

    # Check if token is stored for actions that require the token to exist
    token_is_stored = isTokenStored(token_contract)

    if action == 'add_token':
        if not token_is_stored:
            context.user_data['token_contract'] = token_contract
            await update.message.reply_text(f'Token Contract Address Received: {token_contract}.\n Now, please send the Chat ID.')
            return RECEIVING_CHAT_ID
        else:
            await update.message.reply_text('Token already exists. Use update or delete functions for existing tokens.')
            return ConversationHandler.END

    elif action in ['update_step_size','update_min_limit','update_supply','update_emoji']:
        if token_is_stored:
            context.user_data['token_contract'] = token_contract

            if action == 'update_step_size':
                await update.message.reply_text('Please send the new Step Size.')
                return RECEIVING_STEP_SIZE

            elif action=='update_min_limit':
                await update.message.reply_text('Please send the new Minimum Limit.')
                return RECEIVING_MIN_LIMIT

            elif action=='update_supply':
                await update.message.reply_text('Please send the new Circulation Supply.')
                return RECEIVING_SUPPLY

            elif action=='update_emoji':
                await update.message.reply_text('Please send the new Emoji.')
                return RECEIVING_EMOJI


        else:
            await update.message.reply_text('Token does not exist. Please add the token first or check the contract address.')
            return ConversationHandler.END

    else:
        await update.message.reply_text('Unexpected action. Please start over.')
        return ConversationHandler.END



async def receiveChatID(update: Update, context: CallbackContext) -> int:
    chat_id = update.message.text
    token_contract = context.user_data.get('token_contract', 'No token details recorded.')
    storeTokens(token_contract,chat_id)
    updateChange("addToken",token_contract,chat_id)
    await update.message.reply_text(f'Chat ID received: {chat_id}. Token Details: {token_contract}.')
    return ConversationHandler.END



async def handleTokenDeletion(update: Update, context: CallbackContext) -> int:
    #token_contract = context.user_data.get('token_contract', 'No token details recorded.')
    token_contract = update.message.text
    updateChange("deleteToken",token_contract,0)
    await update.message.reply_text(f'TokenDeleted: {token_contract}')
    return ConversationHandler.END


async def receiveMinLimit(update: Update, context: CallbackContext) -> int:
    token_contract = context.user_data.get('token_contract', 'No token details recorded.')
    minAmountLimit= update.message.text
    updateChange("updateMinLimit",token_contract,minAmountLimit)
    await update.message.reply_text(f'Minimum Amount Limit updated for: {token_contract}')
    return ConversationHandler.END


async def receiveStepSize(update: Update, context: CallbackContext) -> int:
    token_contract = context.user_data.get('token_contract', 'No token details recorded.')
    stepSize= update.message.text
    updateChange("updateStepSize",token_contract,stepSize)
    await update.message.reply_text(f'Step Size updated for: {token_contract}')
    return ConversationHandler.END


async def checkTokenAndRespond(update: Update, context: CallbackContext) -> int:
    token_contract = update.message.text
    if isTokenStored(token_contract):
        await update.message.reply_text(f'Token: {token_contract} Exists')
        return ConversationHandler.END

    else:
        await update.message.reply_text(f'Token: {token_contract} Does NOT Exist')
        return ConversationHandler.END


async def updateCirculationSupply(update: Update, context: CallbackContext) -> int:
    token_contract = context.user_data.get('token_contract', 'No token details recorded.')
    newCirculationSupply= update.message.text
    updateChange("updateSupply",token_contract,newCirculationSupply)
    await update.message.reply_text(f'Circulation Supply updated for: {token_contract}')
    return ConversationHandler.END


async def updateEmoji(update: Update, context: CallbackContext) -> int:
    token_contract = context.user_data.get('token_contract', 'No token details recorded.')
    newEmoji= update.message.text
    updateChange("updateEmoji",token_contract,newEmoji)
    await update.message.reply_text(f'Emoji updated for: {token_contract}')
    return ConversationHandler.END





def botHandler():
    application = Application.builder().token(bot_token).build()
    conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('addtoken', addTokenCommand),
        CommandHandler('deletetoken', deleteTokensCommand),
        CommandHandler('updatesupply', updateSupplyCommand),
        CommandHandler('updateemoji', updateEmojiCommand),
        CommandHandler('updatestepsize', updateStepSizeCommand),
        CommandHandler('updateminlimit', updateMinLimitCommand),
        CommandHandler('checktoken', checkTokenCommand),



    ],
    states={
        RECEIVING_TOKEN_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveTokenContract)],
        RECEIVING_CHAT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveChatID)],
        DELETE_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handleTokenDeletion)],
        RECEIVING_STEP_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveStepSize)],
        RECEIVING_MIN_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveMinLimit)],
        CHECK_TOKEN_AND_RESPOND:[MessageHandler(filters.TEXT & ~filters.COMMAND, checkTokenAndRespond)],
        RECEIVING_SUPPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, updateCirculationSupply)],
        RECEIVING_EMOJI: [MessageHandler(filters.TEXT & ~filters.COMMAND, updateEmoji)],

    },
    fallbacks=[CommandHandler('cancel', lambda update, context: ConversationHandler.END)]
)
    application.add_handler(CommandHandler("start", startConvo))
    application.add_handler(conv_handler)
    application.run_polling()


def run():
    if web3.is_connected()==True:
        print ("Connected to Omax Mainnet")
        if fileExist("Tokens.json"):
            addStoredTokens()
        #addToken(Tara,-1002073756163)
        asyncio.run(blockScan())



if __name__ == '__main__':
    process1 = Process(target=run)
    process2 = Process(target=botHandler)

    process1.start()
    process2.start()

    process1.join()
    process2.join()

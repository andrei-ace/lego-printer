const Alexa = require('ask-sdk-core');
const Util = require('./util');

// The namespace of the custom directive to be sent by this skill
const NAMESPACE = 'Custom.Mindstorms.Gadget';
const NAME_LEARN = 'learn'

const LaunchRequestHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'LaunchRequest';
    },
    handle: async function (handlerInput) {

        let request = handlerInput.requestEnvelope;
        let { apiEndpoint, apiAccessToken } = request.context.System;
        let apiResponse = await Util.getConnectedEndpoints(apiEndpoint, apiAccessToken);
        if ((apiResponse.endpoints || []).length === 0) {
            return handlerInput.responseBuilder
                .speak(`I couldn't find an EV3 Brick connected to this Echo device. Please check to make sure your EV3 Brick is connected, and try again.`)
                .getResponse();
        }

        // Store the gadget endpointId to be used in this skill session
        let endpointId = apiResponse.endpoints[0].endpointId || [];
        Util.putSessionAttribute(handlerInput, 'endpointId', endpointId);

        // Set skill duration to 1 minute (2 30-seconds interval)
        Util.putSessionAttribute(handlerInput, 'duration', 2);
        // Set the token to track the event handler
        const token = handlerInput.requestEnvelope.request.requestId;
        Util.putSessionAttribute(handlerInput, 'token', token);

        return handlerInput.responseBuilder
            .speak("Welcome, how can I help?")
            .withShouldEndSession(false)
            .addDirective(buildStartEventHandler(token, 30000, {}))
            .getResponse();
    }
};
// The request interceptor is used for request handling testing and debugging.
// It will simply log the request in raw json format before any processing is performed.
const RequestInterceptor = {
    process(handlerInput) {
        let { attributesManager, requestEnvelope } = handlerInput;
        let sessionAttributes = attributesManager.getSessionAttributes();

        // Log the request for debug purposes.
        console.log(`=====Request==${JSON.stringify(requestEnvelope)}`);
        console.log(`=========SessionAttributes==${JSON.stringify(sessionAttributes, null, 2)}`);
    }
};

// Generic error handling to capture any syntax or routing errors. If you receive an error
// stating the request handler chain is not found, you have not implemented a handler for
// the intent being invoked or included it in the skill builder below.
const ErrorHandler = {
    canHandle() {
        return true;
    },
    handle(handlerInput, error) {
        console.log(`~~~~ Error handled: ${error.stack}`);
        const speakOutput = `Sorry, I had trouble doing what you asked. Please try again.`;

        return handlerInput.responseBuilder
            .speak(speakOutput)
            .getResponse();
    }
};

// The intent reflector is used for interaction model testing and debugging.
// It will simply repeat the intent the user said. You can create custom handlers
// for your intents by defining them above, then also adding them to the request
// handler chain below.
const IntentReflectorHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'IntentRequest';
    },
    handle(handlerInput) {
        const intentName = Alexa.getIntentName(handlerInput.requestEnvelope);
        const speakOutput = `You just triggered ${intentName}`;

        return handlerInput.responseBuilder
            .speak(speakOutput)
            .getResponse();
    }
};

const HelpIntentHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'IntentRequest'
            && Alexa.getIntentName(handlerInput.requestEnvelope) === 'AMAZON.HelpIntent';
    },
    handle(handlerInput) {
        const speakOutput = 'You can say hello to me! How can I help?';

        return handlerInput.responseBuilder
            .speak(speakOutput)
            .getResponse();
    }
};
const CancelAndStopIntentHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'IntentRequest'
            && (Alexa.getIntentName(handlerInput.requestEnvelope) === 'AMAZON.CancelIntent'
                || Alexa.getIntentName(handlerInput.requestEnvelope) === 'AMAZON.StopIntent');
    },
    handle(handlerInput) {
        const speakOutput = 'Goodbye!';
        return handlerInput.responseBuilder
            .addDirective(buildStopEventHandlerDirective(handlerInput))
            .speak(speakOutput)
            .getResponse();
    }
};
const SessionEndedRequestHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'SessionEndedRequest';
    },
    handle(handlerInput) {
        // Any cleanup logic goes here.
        return handlerInput.responseBuilder
            .addDirective(buildStopEventHandlerDirective(handlerInput))
            .getResponse();
    }
};

const LearnIntentHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'IntentRequest'
            && Alexa.getIntentName(handlerInput.requestEnvelope) === 'LearnIntent';
    },
    handle: function (handlerInput) {

        let letter = Alexa.getSlotValue(handlerInput.requestEnvelope, 'Letter');
        letter = letter.charAt(0).toUpperCase();
        letter = letter.toUpperCase();
        const attributesManager = handlerInput.attributesManager;
        let endpointId = attributesManager.getSessionAttributes().endpointId || [];

        // Set skill duration to 1 minute (2 30-seconds interval)
        Util.putSessionAttribute(handlerInput, 'duration', 2);

        let directive = Util.build(endpointId, NAMESPACE, NAME_LEARN,
            {
                letter: letter
            });

        console.log(directive);

        return handlerInput.responseBuilder
            .speak(`You asked for letter ${letter}.`)
            .addDirective(directive)
            .getResponse();
    }
};

const EventsReceivedRequestHandler = {
    // Checks for a valid token and endpoint.
    canHandle(handlerInput) {
        let { request } = handlerInput.requestEnvelope;
        console.log('Request type: ' + Alexa.getRequestType(handlerInput.requestEnvelope));
        if (request.type !== 'CustomInterfaceController.EventsReceived') return false;

        const attributesManager = handlerInput.attributesManager;
        let sessionAttributes = attributesManager.getSessionAttributes();
        let customEvent = request.events[0];

        // if (sessionAttributes.token !== request.token) {
        //     console.log("Event token doesn't match. Ignoring this event");
        //     return false;
        // }

        // Validate endpoint
        let requestEndpoint = customEvent.endpoint.endpointId;
        if (requestEndpoint !== sessionAttributes.endpointId) {
            console.log("Event endpoint id doesn't match. Ignoring this event");
            return false;
        }
        return true;
    },
    handle(handlerInput) {

        console.log("== Received Custom Event ==");
        let customEvent = handlerInput.requestEnvelope.request.events[0];
        let payload = customEvent.payload;
        let name = customEvent.header.name;

        const token = handlerInput.requestEnvelope.request.requestId;
        Util.putSessionAttribute(handlerInput, 'token', token);

        console.log(customEvent)

        if (name === 'speak') {
            return handlerInput.responseBuilder
                .speak(payload.txt)
                .getResponse();
        }

        if (name === 'done') {
            return handlerInput.responseBuilder
                .speak('How can I help?')
                .addDirective(buildStopEventHandlerDirective(handlerInput))
                .withShouldEndSession(false)
                .getResponse();
        }

        return handlerInput.responseBuilder
            .speak('unknown event')
            .getResponse();
    }
};
const ExpiredRequestHandler = {
    canHandle(handlerInput) {
        return Alexa.getRequestType(handlerInput.requestEnvelope) === 'CustomInterfaceController.Expired'
    },
    handle(handlerInput) {
        console.log("== Custom Event Expiration Input ==");

        const attributesManager = handlerInput.attributesManager;

        let token = handlerInput.attributesManager.getSessionAttributes().token || '';

        let duration = attributesManager.getSessionAttributes().duration || 0;
        if (duration > 0) {
            Util.putSessionAttribute(handlerInput, 'duration', --duration);
            // Extends skill session
            return handlerInput.responseBuilder
                .addDirective(buildStartEventHandler(token, 30000, {}))
                .getResponse();
        }
        else {
            // End skill session
            return handlerInput.responseBuilder
                .speak("Skill duration expired. Goodbye.")
                .withShouldEndSession(true)
                .getResponse();
        }
    }
};

// The SkillBuilder acts as the entry point for your skill, routing all request and response
// payloads to the handlers above. Make sure any new handlers or interceptors you've
// defined are included below. The order matters - they're processed top to bottom.
exports.handler = Alexa.SkillBuilders.custom()
    .addRequestHandlers(
        LaunchRequestHandler,
        LearnIntentHandler,
        EventsReceivedRequestHandler,
        ExpiredRequestHandler,
        HelpIntentHandler,
        CancelAndStopIntentHandler,
        SessionEndedRequestHandler,
        IntentReflectorHandler, // make sure IntentReflectorHandler is last so it doesn't override your custom intent handlers
    )
    .addRequestInterceptors(RequestInterceptor)
    .addErrorHandlers(
        ErrorHandler,
    )
    .lambda();

function buildStartEventHandler(token, timeout = 30000, payload) {
    return {
        type: "CustomInterfaceController.StartEventHandler",
        token: token,
        expiration: {
            durationInMilliseconds: timeout,
            expirationPayload: payload
        }
    };
}

function buildStopEventHandlerDirective(handlerInput) {
    let token = handlerInput.attributesManager.getSessionAttributes().token || '';
    return {
        "type": "CustomInterfaceController.StopEventHandler",
        "token": token
    }
}

Note to agent: This best practice doc is written by a internal user who builds a Sales Assistant Agent for Snowflake's own sales team.
# Agent Instruction Best Practices

## Snowflake Intelligence

Sait Izmit \- Principle Product Manager, September 5, 2025

## Purpose of this Document

To share best practices on how to write agent instructions for developing business-user facing agents in Snowflake Intelligence.

## Get Your Requirements Right\!

Don’t just connect some data to your agent and hope that everything will magically work. At the end you are developing a product. Make sure that you follow the standard product development best practices starting with defining your products requirements\!

Interview your users and try to answer these questions:

* Who are your users?   
* Do you have any secondary users you need to consider?  
* What are their critical user journeys (CUJs)?  
* What kind of needs do they have as part of those CUJs and to what kind of user questions can those potentially translate to?  
* What are the resulting data requirements from those needs?  
* What is the prioritization among those?  
* … 

## Testing is Key for a Reliable Agent

Make sure to have a question test bed early in the project. Rather than including only the questions that the agent is designed to answer, try to include any type of question the user might end up asking independent of the fact that your agent is designed to answer those or not. At the end you are putting a free form chat interface in front of them where they can ask anything. You are responsible for designing against ‘foreseeable misuse’\!

Here is an example format you can use to structure your test questions and their results:

| Persona | CUJ | Question | Alternative Questions | Should it answer? | Does it answer | Accuracy | Stability |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| … | … | … | … | … | … | … | … |

Even though testing might feel time consuming, it is essential to go through your test questions early in the project to establish a baseline of your agent quality. Those initial results will give you a lot of pointers on where you need to improve either your agent instructions or underlying data. Throughout the project you can re-test to update your test results baseline as you improve your agent.

Target for 50-100 questions to get started with depending on the complexity of your agent. Over time you can enrich/replace those questions with live questions from users.

## Give You Agent an Identify & Provide Context

Here is an example from our sales assistant:

Your Role & Scope: Your name is '\<agent’s name\>'. You are a helpful agent to support internal sales teams in their day to day operations by answering their knowledge and data questions to help them improve their productivity and effectiveness.

Your Users: Unless identified differently by the user, your users are usually either Account Executives (AEs), Solution Engineers (SEs), Sales Development Reps (SDRs) and/or sales/district managers & leaders who interact with you through a chat UI.

Background on Sales Organization & How they Operate: 

* Snowflake is a cloud-based data storage and analytics company that offers a platform for data warehousing, data lakes, data engineering, and various data-related workloads, including AI/ML applications.   
* AEs, SEs and SDRs work together to acquire new customers, onboard them and grow their Snowflake consumption & new product adoption over time. In order to do that they follow an internal process called '\<process name\>' which consists of \<process details\>.   
* AEs and SEs use Salesforce to track their pipelines and customer engagements. They log 'Opportunities' and 'Use Cases' in Salesforce to progress their stages over time.  \<more operational details\>  
* Sales teams are organized across different segments: \<organizational details\>  
* …

## Set the Tone & Define Guardrails

Here is an example from our sales assistant:

Style & Format:

* Be very concise in your responses.  
* Be polite, helpful and sound professional.  
* Show results in tables and charts as much as possible.  
* …

Safeguards: 

* English is your default language to communicate with your users however \<language instructions\>  
* Never promise any results or make any agreements.   
* Be polite and serious even when the user is not.   
* Decline to discuss sensitive topics such as religion, race, \<list of topics\>  
* Only engage in conversations that relate to your defined scope.  
* …

Disclaimers:

* When answering legal-related questions, show the following disclaimer at the end of your response: \<disclaimer details\>   
* Remind users of row-based access controls when providing answers based on \<tool names\>.

## Clarify Which Tool is Meant for What Purpose

If your agent is using multiple tools and if there are overlap between your tools with respect to types of data, your agent can run into quality/stability issues where it may sometimes end up using the wrong tool. Therefore, it is a good practice to make it clear to your agent, which tools are more suitable for certain types of questions. 

Here is an example from our internal sales assistant:

Depending on the type of user question, you should use/prioritize the following tools:

* For product and sales process related knowledge questions use \<tool name\>. Here are some sample questions you might get: ‘What is the value of Iceberg Tables?’, ‘What are the common data platform security requirements and certifications in the healthcare industry?’ …

* \- For Use Case related questions use \<tool name\>. Here are some sample questions you might get for this: …

* \- For Opportunities, Bookings, Deals related questions use \<tool name\>. Here are some sample questions you might get for this: …  
* …

## Telling an Agent What NOT to Do is 50% of the Work\!

Most quality issues are encountered when agents rely on questions that they are not supposed to answer. This can be due to, for example, data/information that the agent doesn’t have access to. In such cases, agents are likely to reason based on their internal knowledge and respond back with wrong answers (hallucinations). Therefore, it is essential to instruct the agent on what kind of questions it shouldn’t answer and this should be part of your detailed testing to identify & validate as well.

Here is an example from our internal sales assistant:

* Currently you don't have access to \<type of data\>. If you get any questions requiring such data, you should kindly decline user requests informing them that you currently don't have access to such data yet. 

In some cases, rather than not providing an answer at all, you can instruct the agent to rely back with related information despite the fact that the agent is not able to answer the exact question the user is asking:

* If you get questions about use case win rates, inform the user that you are not able to calculate win rates for use cases. Instead display the number of use cases by use case stage. Do not try to calculate a win rate yourself.

## Provide General Guidelines based on Business Practices

This is where you bring in details about your internal best practices, terminology, and expected behaviors. 

Here are some examples from our internal sales assistant:

* When drafting outreach emails, follow these best practices: keep subject lines short; avoid statements \<language instructions\>; keep the email brief with roughly \<word count limits\> words; \<other email best practices\>

* If the user asks about "current" data, use today or the last day for which you have the data. If the user asks about "recent" data, use the last 30 days (if you don’t have data for last 30 days then use last 7 days). 

* If you get questions about sales pipeline health, present total value and number of opportunities by opportunity stage. Compare these numbers to previous year's numbers top show percent change.  The user might ask this question specific for a customer, region or sales team. If the user hasn't defined any specifics, then assume global numbers.

* If the user asks for externally sharable decks, provide a list of decks which you think might be externally sharable however even when you are convinced that these decks are approved for external sharing, still in your final response to the user include a text disclaimer that the user should review the provided decks to determine if they are indeed approved for external sharing.

## Implement Detailed Workflows & Rich Summaries

You can create rich summaries and/or workflow automations making it easier for your users without the need for them to write complex user queries & store those somewhere for later use. By doing that you can also standardize the approach across users while leveling things up for everyone. 

Here is an example of how we provide a book-of-business summaries to sales professionals using our internal sales assistant:

If the user wants to get an update or summary of their book/accounts, using questions like 'Summarize my accounts’', 'Summarize my book’, ‘Any update with my accounts’, ‘what is recent with my book of business’, please use \<tool name\> to get the list of accounts where they are the account owner, including each customer's salesforce\_account\_id. Then use the salesforce\_account\_id list from that step in all following tools, and show results in a table as much as possible.

* Use \<tool name\> to show a list of accounts in a table including their last 90 day consumption, last 90 days growth rate, \<list of data points\>

* Use  \<tool name\> to show the top open pipeline by value including \<list of data points\>

* Use \<tool name\>  to show contract status, including account name, contract start date, end date, \<list of data points\>

* Use \<tool name\>  to list of top 10 active use cases by value including their use case description, value,  \<list of data points\>

* Use \<tool name\>  tool to summarize major news in the last 7 days for any of the accounts  

* Use \<tool name\>  to summarize if any of the accounts have any critical severity customer support tickets created in the last 7 days

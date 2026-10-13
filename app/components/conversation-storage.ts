import type {Conversation,ConversationCreate,ConversationPage,MessageCreate,MessagePage} from '../lib/conversation-contract';
type Client = {
  session:(fresh?:boolean,signal?:AbortSignal)=>Promise<void>;
  create:(payload:ConversationCreate,signal?:AbortSignal)=>Promise<Conversation>;
  append:(id:string,payload:MessageCreate,signal?:AbortSignal)=>Promise<unknown>;
  list:(cursor?:string|null,signal?:AbortSignal)=>Promise<ConversationPage>;
  get:(id:string,before?:number|null,signal?:AbortSignal)=>Promise<MessagePage>;
  delete:(id:string,signal?:AbortSignal)=>Promise<void>;
  deleteAll:(signal?:AbortSignal)=>Promise<number>;
};
export class ConversationStorage {
  consent=false;epoch=0;active:string|null=null;items:Conversation[]=[];nextCursor:string|null=null;beforeSequence:number|null=null;loading=false;
  error:string|null=null;pending:MessageCreate[]=[];
  private createId=crypto.randomUUID();private creatingTitle:string|null=null;private running:Promise<void>|null=null;private earlierBusy=false;
  private controller=new AbortController();
  private client:Client;private changed:()=>void;
  constructor(client:Client,changed:()=>void){this.client=client;this.changed=changed;}
  setConsent(value:boolean){this.consent=value;if(!value){this.invalidate();this.pending=[];this.error=null;}this.changed();}
  invalidate(){this.epoch++;this.controller.abort();this.controller=new AbortController();this.running=null;this.loading=false;this.earlierBusy=false;}
  newConversation(){this.invalidate();this.active=null;this.createId=crypto.randomUUID();this.creatingTitle=null;this.pending=[];this.error=null;this.beforeSequence=null;this.loading=false;this.changed();}
  async refresh(more=false){
    const epoch=this.epoch;
    try {const page=await this.client.list(more?this.nextCursor:null,this.controller.signal);if(epoch!==this.epoch)return;this.items=more?[...this.items,...page.items.filter(item=>!this.items.some(old=>old.id===item.id))]:page.items;this.nextCursor=page.nextCursor;this.changed();}
    catch(error){if(epoch===this.epoch&&error instanceof Error&&error.message!=='SESSION_REQUIRED'){this.error=error.message;this.changed();}}
  }
  async saveMessage(message:MessageCreate,epoch:number){
    if(!this.consent||epoch!==this.epoch)return;
    this.pending.push(message);this.changed();
    if(!this.error)await this.flush();
  }
  async retrySave(){this.error=null;await this.flush();}
  private flush():Promise<void>{
    if(this.running)return this.running;
    if(!this.consent||!this.pending.length)return Promise.resolve();
    const epoch=this.epoch,signal=this.controller.signal;
    const job=(async()=>{
      try {
        if(!this.consent||!this.pending.length)return;
        await this.client.session(false,signal);
        if(epoch!==this.epoch||!this.consent)return;
        if(!this.active){this.creatingTitle??=this.pending[0].content.trim().slice(0,80)||'새 대화';const value=await this.client.create({storageConsent:true,createRequestId:this.createId,title:this.creatingTitle},signal);if(epoch!==this.epoch||!this.consent)return;this.active=value.id;}
        while(this.consent&&epoch===this.epoch&&this.pending.length){const current=this.pending[0];await this.client.append(this.active!,current,signal);if(epoch!==this.epoch)return;this.pending.shift();this.changed();}
        await this.refresh();
      }catch(error){if(epoch===this.epoch){this.error=error instanceof Error?error.message:'STORAGE_UNAVAILABLE';this.changed();}}
      finally{if(epoch===this.epoch){this.running=null;this.changed();if(this.pending.length&&!this.error&&this.consent)queueMicrotask(()=>void this.flush());}}
    })();this.running=job;return job;
  }
  async loadConversation(id:string):Promise<MessagePage|null>{
    this.newConversation();this.active=id;this.loading=true;const epoch=this.epoch;this.changed();
    try {const page=await this.client.get(id,null,this.controller.signal);if(epoch!==this.epoch)return null;this.beforeSequence=page.beforeSequence;return page;}
    catch(error){if(epoch===this.epoch){this.error=error instanceof Error?error.message:'STORAGE_UNAVAILABLE';this.changed();}return null;}
    finally{if(epoch===this.epoch){this.loading=false;this.changed();}}
  }
  async loadEarlier():Promise<MessagePage|null>{
    if(!this.active||!this.beforeSequence||this.earlierBusy)return null;
    const epoch=this.epoch,boundary=this.beforeSequence;this.earlierBusy=true;
    try {const page=await this.client.get(this.active,boundary,this.controller.signal);if(epoch!==this.epoch||this.beforeSequence!==boundary)return null;this.beforeSequence=page.beforeSequence;this.changed();return page;}
    catch(error){if(epoch===this.epoch){this.error=error instanceof Error?error.message:'STORAGE_UNAVAILABLE';this.changed();}return null;}
    finally{if(epoch===this.epoch)this.earlierBusy=false;}
  }
  async deleteConversation(id:string){
    if(this.active===id)this.newConversation();else this.invalidate();const epoch=this.epoch;
    try {await this.client.delete(id,this.controller.signal);if(epoch===this.epoch){await this.refresh();if(this.consent&&this.pending.length&&!this.error)await this.flush();}}
    catch(error){if(epoch===this.epoch){this.error=error instanceof Error?error.message:'STORAGE_UNAVAILABLE';this.changed();}}
  }
  async deleteAllConversations(){
    this.newConversation();const epoch=this.epoch;
    try {await this.client.deleteAll(this.controller.signal);if(epoch===this.epoch)await this.refresh();}
    catch(error){if(epoch===this.epoch){this.error=error instanceof Error?error.message:'STORAGE_UNAVAILABLE';this.changed();}}
  }
  async newSession(){this.newConversation();this.items=[];try{await this.client.session(true,this.controller.signal);await this.refresh();}catch{this.error='STORAGE_UNAVAILABLE';this.changed();}}
}
